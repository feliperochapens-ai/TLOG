import os, sqlite3, hashlib, hmac, secrets, calendar, html
from datetime import date, datetime, timedelta
from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title='TLOG | Gestão de Atividades', page_icon='📊', layout='wide', initial_sidebar_state='expanded')
DB = os.environ.get('TLOG_DB_PATH', os.path.join(os.path.dirname(__file__), 'atividades.db'))

CSS = """
<style>
/* Fundo principal */
[data-testid="stAppViewContainer"] {
    background-color: #F3F5FA !important;
    color: #18243C !important;
}

/* Área central */
[data-testid="stAppViewContainer"] .block-container {
    padding-top: 4rem !important;
    padding-bottom: 2rem !important;
    max-width: 1550px !important;
}

/* Textos gerais */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {
    color: #18243C;
}

/* Barra lateral */
[data-testid="stSidebar"] {
    background-color: #10182E !important;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #FFFFFF !important;
}

/* Campos e seletores */
[data-baseweb="input"] input,
[data-baseweb="select"] > div,
textarea {
    background-color: #FFFFFF !important;
    color: #18243C !important;
}

/* Rótulos */
[data-testid="stWidgetLabel"] p {
    color: #26364F !important;
    font-weight: 500 !important;
}

/* Abas */
button[data-baseweb="tab"] {
    color: #26364F !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #607BF0 !important;
}

/* Cabeçalho TLOG */
.tlog-head {
    background: #10182E !important;
    color: #FFFFFF !important;
    border-radius: 9px;
    padding: 18px 24px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.tlog-head * {
    color: #FFFFFF !important;
}

/* Banner principal */
.tlog-banner {
    background: linear-gradient(
        105deg, #607BF0, #7C4AA7
    ) !important;
    border-radius: 11px;
    padding: 24px;
    margin-bottom: 20px;
}

.tlog-banner,
.tlog-banner * {
    color: #FFFFFF !important;
}

/* Cartões e formulários */
[data-testid="stForm"] {
    background: #FFFFFF !important;
    border: 1px solid #E4E9F3;
    border-radius: 12px;
    padding: 16px;
}

/* Alertas informativos */
[data-testid="stAlert"] p {
    color: inherit !important;
}
/* Botões de exportação: branco e letras pretas */
[data-testid="stDownloadButton"] button {
    background-color: #FFFFFF !important;
    color: #000000 !important;
    border: 1px solid #C8D1DF !important;
}
[data-testid="stDownloadButton"] button * { color: #000000 !important; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

def connect():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def hash_pw(pw, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+'$'+hashlib.pbkdf2_hmac('sha256',pw.encode(),bytes.fromhex(salt),220000).hex()

def verify_pw(pw, stored):
    try:
        salt,_=stored.split('$',1)
        return hmac.compare_digest(hash_pw(pw,salt),stored)
    except Exception:return False



def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(
                role IN ('admin','coordenador','colaborador')
            ),
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS segments(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            segment_id INTEGER NOT NULL REFERENCES segments(id),
            assignee_id INTEGER NOT NULL REFERENCES users(id),
            due_day INTEGER NOT NULL DEFAULT 10,
            working_day INTEGER NOT NULL DEFAULT 0,
            recurring INTEGER NOT NULL DEFAULT 1,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS instances(
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            period TEXT NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            completed_at TEXT,
            completed_by INTEGER REFERENCES users(id),
            approved_at TEXT,
            approved_by INTEGER REFERENCES users(id),
            notes TEXT DEFAULT '',
            UNIQUE(task_id,period)
        );

        CREATE INDEX IF NOT EXISTS idx_instances_period
        ON instances(period);
        """)

        c.executescript("""
        CREATE TABLE IF NOT EXISTS branches(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS licenses(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            branch_id INTEGER NOT NULL REFERENCES branches(id),
            issuer TEXT DEFAULT '', document_number TEXT DEFAULT '',
            issued_on TEXT, expires_on TEXT NOT NULL,
            responsible_id INTEGER REFERENCES users(id),
            notes TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS license_renewals(
            id INTEGER PRIMARY KEY,
            license_id INTEGER NOT NULL REFERENCES licenses(id),
            old_expires_on TEXT NOT NULL,
            new_expires_on TEXT NOT NULL,
            renewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            renewed_by INTEGER REFERENCES users(id)
        );
        """)

        c.executemany(
            "INSERT OR IGNORE INTO segments(name) VALUES(?)",
            [
                ("Fechamento",),
                ("Lançamento de contas fixas",),
                ("Cartão de crédito",)
            ]
        )

        admin_password = st.secrets.get(
            "TLOG_ADMIN_PASSWORD", None
        )

        if not admin_password:
            st.error(
                "Configure TLOG_ADMIN_PASSWORD no Streamlit Secrets."
            )
            st.stop()

        admin = c.execute(
            "SELECT id FROM users WHERE username = ?",
            ("admin",)
        ).fetchone()

        if admin is None:
            c.execute(
                """
                INSERT INTO users
                (name,username,password,role,active)
                VALUES(?,?,?,?,?)
                """,
                (
                    "Administrador",
                    "admin",
                    hash_pw(admin_password),
                    "admin",
                    1
                )
            )

        elif st.secrets.get(
            "TLOG_RESET_ADMIN_PASSWORD", False
        ):
            c.execute(
                """
                UPDATE users
                SET password=?,role='admin',active=1
                WHERE username='admin'
                """,
                (hash_pw(admin_password),)
            )

        c.commit()


def q(sql,args=()):
    with connect() as c:return pd.read_sql_query(sql,c,params=args)

def execute(sql,args=()):
    with connect() as c:return c.execute(sql,args).lastrowid

def rows(sql,args=()):
    with connect() as c:return c.execute(sql,args).fetchall()

def due_date(year,month,day,working):
    if not working:return date(year,month,min(day,calendar.monthrange(year,month)[1]))
    d=date(year,month,1); n=0
    while d.month==month:
        if d.weekday()<5:
            n+=1
            if n==day:return d
        d+=timedelta(days=1)
    return date(year,month,calendar.monthrange(year,month)[1])

def generate_period(period):
    year,month=map(int,period.split('-'))
    with connect() as c:
        for t in c.execute('SELECT * FROM tasks WHERE active=1 AND recurring=1').fetchall():
            due=due_date(year,month,t['due_day'],t['working_day'])
            c.execute('INSERT OR IGNORE INTO instances(task_id,period,due_date) VALUES(?,?,?)',(t['id'],period,due.isoformat()))

def data(period):
    return q('''SELECT i.id,i.task_id,t.title AS Atividade,s.name AS Segmentação,u.name AS Responsável,u.id AS assignee_id,
      i.due_date AS Prazo,i.status AS Status,i.completed_at AS Conclusão,i.approved_at AS Aprovação,i.notes AS Observações,
      t.requires_approval AS Exige_aprovação,i.period AS Período
      FROM instances i JOIN tasks t ON i.task_id=t.id JOIN segments s ON t.segment_id=s.id JOIN users u ON t.assignee_id=u.id
      WHERE i.period=? ORDER BY i.due_date,s.name,t.title''',(period,))

def status_label(row):
    if row['Status']=='Pendente' and row['Prazo']<date.today().isoformat():return 'Atrasada'
    return row['Status']

def excel_bytes(df):
    out=BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Atividades')
        ws=writer.sheets['Atividades'];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:
            letter=col[0].column_letter
            ws.column_dimensions[letter].width=min(45,max(14,max(len(str(cell.value or '')) for cell in col)+3))
    return out.getvalue()

init_db()
if 'user_id' not in st.session_state:
    st.markdown('<div class="tlog-head"><b>G R U P O &nbsp; TLOG</b><b>Gestão de Atividades</b></div>',unsafe_allow_html=True)
    st.title('Entrar no sistema')
    if st.session_state.get('initial_password'):
        st.warning('Primeiro acesso — usuário: admin | senha provisória: '+st.session_state['initial_password']+'\n\nAltere a senha em Administração após entrar. Guarde-a antes de fechar esta tela.')
    with st.form('login'):
        login=st.text_input('Usuário')
        senha=st.text_input('Senha',type='password')
        if st.form_submit_button('Entrar',type='primary'):
            user=rows('SELECT * FROM users WHERE username=? AND active=1',(login.strip(),))
            if user and verify_pw(senha,user[0]['password']):
                st.session_state['user_id']=user[0]['id'];st.session_state.pop('initial_password',None);st.rerun()
            else:st.error('Usuário ou senha inválidos.')
    st.stop()

user=rows('SELECT * FROM users WHERE id=? AND active=1',(st.session_state['user_id'],))
if not user:
    st.session_state.pop('user_id',None);st.rerun()
user=user[0];manager=user['role'] in ('admin','coordenador');admin=user['role']=='admin'
with st.sidebar:
    st.markdown('## G R U P O  **TLOG**')
    st.caption(user['name']+' · '+user['role'].capitalize())
    pages=['📊 Dashboard','📑 Dashboard Licenças','☑️ Minhas atividades']+(['📋 Equipe e aprovações'] if manager else [])+(['⚙️ Administração'] if admin else [])+['🔒 Minha senha']
    page=st.radio('Navegação',pages,label_visibility='collapsed')
    st.divider()
    if st.button('Sair',use_container_width=True):
        st.session_state.pop('user_id',None);st.rerun()

st.markdown('<div class="tlog-head"><b>G R U P O &nbsp; TLOG</b><b>Gestão de Atividades</b><small>'+user['name']+'</small></div>',unsafe_allow_html=True)
st.markdown('<div class="tlog-banner"><h2>'+html.escape(page[2:])+'</h2><p>'+('Gestão de licenças, alvarás e vencimentos por filial.' if page.startswith('📑') else 'Acompanhe e organize as atividades mensais da equipe.')+'</p></div>',unsafe_allow_html=True)

def pick_period(key='period'):
    today=date.today();months=pd.date_range(date(today.year-1,1,1),date(today.year+2,12,1),freq='MS')
    opts=[d.strftime('%Y-%m') for d in months]
    return st.selectbox('Mês de referência',opts,index=opts.index(today.strftime('%Y-%m')),format_func=lambda x:date.fromisoformat(x+'-01').strftime('%m/%Y'),key=key)

if page.startswith('📊') or page.startswith('☑️') or page.startswith('📋'):
    period=pick_period()
    generate_period(period)
    df=data(period)
    if not manager:df=df[df['assignee_id']==user['id']].copy()
    if not df.empty:df['Situação']=df.apply(status_label,axis=1)

# Componentes de visualização: cores padrão do Grupo TLOG.
TLOG_BLUE = '#607BF0'
TLOG_YELLOW = '#E8B247'
TLOG_RED = '#DF4A59'


def status_color(status):
    if status in ('Concluída', 'Aprovada', 'Regular'):
        return TLOG_BLUE
    if status in ('Atrasada', 'Vencida'):
        return TLOG_RED
    return TLOG_YELLOW


def styled_table(frame, *, expired_column=None, height=350, header_text='#FFFFFF'):
    """Tabela HTML segura, com cabeçalho fixo e rolagem."""
    if frame.empty:
        st.info('Nenhum registro corresponde aos filtros.')
        return
    safe = frame.copy().fillna('')
    html_table = safe.to_html(index=False, escape=True, border=0, classes='tlog-table')
    if expired_column is not None:
        import re
        # A situação foi escapada pelo pandas; destaque apenas linhas com situação Vencida.
        html_table = re.sub(r'<tr>(?:(?!</tr>).)*?<td>Vencida</td>(?:(?!</tr>).)*?</tr>',
                            lambda m: m.group(0).replace('<tr>', '<tr class="expired">', 1),
                            html_table, flags=re.DOTALL)
    markup = '''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;background:#fff;font-family:Arial,sans-serif}
    .wrap{height:HEIGHTpx;overflow:auto;border:1px solid #DDE4F0;border-radius:9px;background:#fff;box-sizing:border-box}
    table{width:100%;border-collapse:collapse;font-size:12px}
    thead th{position:sticky;top:0;z-index:1;background:#607BF0!important;color:HEADER!important;
        font-weight:700;text-align:left;padding:11px 8px;white-space:nowrap}
    tbody td{background:#fff;color:#000;border-bottom:1px solid #E4E9F3;padding:10px 8px}
    tbody tr.expired td{background:#DF4A59!important;color:#fff!important;font-weight:600}
    </style></head><body><div class="wrap">'''.replace('HEIGHT', str(height)).replace('HEADER', header_text) + html_table + '</div></body></html>'
    components.html(markup, height=height + 8, scrolling=False)


@st.dialog('Detalhamento de atividades', width='large')
def activity_dialog(label, filtered, period):
    st.subheader(label)
    st.caption(f'Mês de referência: {period[5:7]}/{period[:4]} · {len(filtered)} atividade(s)')
    cols = ['Atividade', 'Segmentação', 'Responsável', 'Prazo', 'Situação', 'Observações']
    display = filtered[cols].copy()
    if not display.empty:
        display['Prazo'] = pd.to_datetime(display['Prazo']).dt.strftime('%d/%m/%Y')
    styled_table(display, height=300)
    st.download_button('⬇ Exportar atividades', excel_bytes(display),
                       file_name=f'TLOG_detalhamento_{period}.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if st.button('Fechar janela', key='close_activity_dialog'):
        st.rerun()


@st.dialog('Detalhamento de licenças', width='large')
def licenses_dialog(label, filtered):
    st.subheader(label)
    st.caption(f'{len(filtered)} licença(s)')
    cols = ['Licença', 'Filial', 'Vencimento', 'Situação']
    styled_table(filtered[cols], expired_column='Situação', height=300, header_text='#000000')
    st.download_button('⬇ Exportar licenças', excel_bytes(filtered[cols]),
                       file_name='TLOG_licencas.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if st.button('Fechar janela', key='close_license_dialog'):
        st.rerun()


if page.startswith('📊'):
    if df.empty:
        st.info('Nenhuma atividade cadastrada para este mês.')
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            seg = st.multiselect('Segmentação', sorted(df['Segmentação'].dropna().unique()))
        with f2:
            people = st.multiselect('Responsável', sorted(df['Responsável'].dropna().unique()))
        with f3:
            statuses = st.multiselect('Situação', sorted(df['Situação'].dropna().unique()))
        view = df.copy()
        if seg:
            view = view[view['Segmentação'].isin(seg)]
        if people:
            view = view[view['Responsável'].isin(people)]
        if statuses:
            view = view[view['Situação'].isin(statuses)]

        categories = [
            ('Atividades previstas', view, TLOG_BLUE),
            ('Concluídas / aprovadas', view[view['Situação'].isin(['Concluída', 'Aprovada'])], TLOG_BLUE),
            ('Pendentes / em aprovação', view[view['Situação'].isin(['Pendente', 'Aguardando aprovação'])], TLOG_YELLOW),
            ('Atrasadas', view[view['Situação'] == 'Atrasada'], TLOG_RED),
        ]
        card_cols = st.columns(4)
        for i, ((label, subset, color), col) in enumerate(zip(categories, card_cols)):
            with col:
                st.markdown(f'<div style="background:#fff;border:1px solid #E4E9F3;border-top:4px solid {color};padding:10px 14px;border-radius:10px;color:#18243C"><div style="font-size:12px">{label}</div><div style="font-size:28px;font-weight:700">{len(subset)}</div></div>', unsafe_allow_html=True)
                if st.button('Ver atividades ↗', key=f'activity_card_{i}', use_container_width=True):
                    activity_dialog(label, subset, period)
        done = len(categories[1][1])
        total = len(view)
        st.progress(done / total if total else 0, text=f'Progresso de conclusão: {done}/{total} ({done / total:.0%})' if total else 'Sem atividades')

        left, right = st.columns([1.15, 1], gap='large')
        with left:
            st.subheader('Análise de atividades')
            mode = st.radio('Tipo de análise', ['Segmentação', 'Responsável', 'Histórico'],
                            horizontal=True, label_visibility='collapsed')
            if mode == 'Histórico':
                # Histórico respeita mês, segmentação, responsável e situação selecionados.
                first = (date.fromisoformat(period + '-01') - timedelta(days=180)).strftime('%Y-%m')
                hsql = '''SELECT i.period AS Período, s.name AS Segmentação,
                    u.name AS Responsável, i.status AS Status, i.due_date AS Prazo
                    FROM instances i JOIN tasks t ON i.task_id=t.id
                    JOIN segments s ON t.segment_id=s.id
                    JOIN users u ON t.assignee_id=u.id
                    WHERE i.period BETWEEN ? AND ?'''
                args = [first, period]
                if not manager:
                    hsql += ' AND t.assignee_id=?'
                    args.append(user['id'])
                hist = q(hsql, tuple(args))
                if not hist.empty:
                    hist['Situação'] = hist.apply(status_label, axis=1)
                    if seg:
                        hist = hist[hist['Segmentação'].isin(seg)]
                    if people:
                        hist = hist[hist['Responsável'].isin(people)]
                    if statuses:
                        hist = hist[hist['Situação'].isin(statuses)]
                if hist.empty:
                    st.info('Sem histórico para os filtros selecionados.')
                else:
                    hist['Concluída'] = hist['Situação'].isin(['Concluída', 'Aprovada']).astype(int)
                    monthly = hist.groupby('Período').agg(Total=('Concluída', 'size'), Concluídas=('Concluída', 'sum')).reset_index()
                    monthly['Conclusão (%)'] = (100 * monthly['Concluídas'] / monthly['Total']).round(1)
                    fig = px.line(monthly, x='Período', y='Conclusão (%)', markers=True,
                                  range_y=[0, 100], color_discrete_sequence=[TLOG_BLUE])
                    fig.update_layout(height=340, margin=dict(t=20,b=20), font_color='#18243C',
                                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, use_container_width=True)
            elif view.empty:
                st.info('Nenhuma atividade corresponde aos filtros.')
            else:
                field = 'Segmentação' if mode == 'Segmentação' else 'Responsável'
                group = view.groupby([field, 'Situação']).size().reset_index(name='Quantidade')
                fig = px.bar(group, x=field, y='Quantidade', color='Situação', barmode='stack',
                             color_discrete_map={
                                 'Concluída':TLOG_BLUE, 'Aprovada':TLOG_BLUE,
                                 'Pendente':TLOG_YELLOW, 'Aguardando aprovação':TLOG_YELLOW,
                                 'Atrasada':TLOG_RED})
                fig.update_layout(xaxis_title='', legend_title='', height=340,
                                  margin=dict(t=20,b=20), font_color='#18243C',
                                  paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True)
        with right:
            st.subheader('Agenda de vencimentos')
            agenda = view.sort_values(['Prazo', 'Atividade']).copy()
            if not agenda.empty:
                agenda['Vencimento'] = pd.to_datetime(agenda['Prazo']).dt.strftime('%d/%m/%Y')
                agenda = agenda[['Vencimento', 'Atividade', 'Segmentação', 'Responsável', 'Situação']]
                styled_table(agenda, height=338)
                st.download_button('⬇ Exportar vencimentos', excel_bytes(agenda),
                                   file_name=f'TLOG_vencimentos_{period}.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            else:
                st.info('Nenhum vencimento corresponde aos filtros.')

        st.subheader('Detalhamento')
        detail_cols = ['Atividade', 'Segmentação', 'Responsável', 'Prazo', 'Situação', 'Conclusão', 'Observações']
        st.dataframe(view[detail_cols], hide_index=True, use_container_width=True)
        st.download_button('⬇ Exportar Excel', excel_bytes(view[detail_cols]),
                           file_name=f'TLOG_atividades_{period}.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

elif page.startswith('📑'):
    st.caption('Acompanhamento de licenças e alvarás cadastrados por unidade.')
    raw = q('''SELECT l.id, l.name AS Licença, b.name AS Filial,
        l.issuer AS Órgão, l.document_number AS Número,
        l.issued_on AS Emissão, l.expires_on AS Data_vencimento,
        u.name AS Responsável, l.notes AS Observações
        FROM licenses l JOIN branches b ON l.branch_id=b.id
        LEFT JOIN users u ON l.responsible_id=u.id
        WHERE l.active=1 ORDER BY l.expires_on, l.name''')
    if raw.empty:
        st.info('Nenhuma licença cadastrada. Um administrador pode cadastrar filiais e licenças em Administração → Licenças.')
    else:
        today = date.today()
        raw['Dias restantes'] = (pd.to_datetime(raw['Data_vencimento']).dt.date - today).apply(lambda d: d.days)
        raw['Situação'] = raw['Dias restantes'].apply(lambda d: 'Vencida' if d < 0 else ('A vencer' if d <= 30 else 'Regular'))
        raw['Vencimento'] = pd.to_datetime(raw['Data_vencimento']).dt.strftime('%d/%m/%Y')
        bcol, scol = st.columns(2)
        with bcol:
            selected_branches = st.multiselect('Filial / Unidade', sorted(raw['Filial'].unique()))
        with scol:
            selected_status = st.multiselect('Situação da licença', ['Regular', 'A vencer', 'Vencida'])
        lv = raw.copy()
        if selected_branches:
            lv = lv[lv['Filial'].isin(selected_branches)]
        if selected_status:
            lv = lv[lv['Situação'].isin(selected_status)]
        license_cards = [
            ('Total', lv, TLOG_BLUE),
            ('Regulares', lv[lv['Situação']=='Regular'], TLOG_BLUE),
            ('A vencer (30 dias)', lv[lv['Situação']=='A vencer'], TLOG_YELLOW),
            ('Vencidas', lv[lv['Situação']=='Vencida'], TLOG_RED),
        ]
        for i, ((label, subset, color), col) in enumerate(zip(license_cards, st.columns(4))):
            with col:
                st.markdown(f'<div style="background:#fff;border:1px solid #E4E9F3;border-top:4px solid {color};padding:10px 14px;border-radius:10px;color:#18243C"><div style="font-size:12px">{label}</div><div style="font-size:28px;font-weight:700">{len(subset)}</div></div>', unsafe_allow_html=True)
                if st.button('Ver licenças ↗', key=f'license_card_{i}', use_container_width=True):
                    licenses_dialog(label, subset)
        st.subheader('Controle de licenças e vencimentos')
        license_cols = ['Licença', 'Filial', 'Vencimento', 'Situação']
        styled_table(lv[license_cols], expired_column='Situação', height=380, header_text='#000000')
        st.download_button('⬇ Exportar licenças', excel_bytes(lv[license_cols]),
                           file_name='TLOG_licencas.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

elif page.startswith('☑️'):
    mine=df[df['assignee_id']==user['id']].copy()
    if mine.empty:st.info('Você não possui atividades neste mês.')
    for _,r in mine.iterrows():
        with st.expander(f"{'🟢' if r['Situação'] in ('Concluída','Aprovada') else '🟡'} {r['Atividade']}  ·  {r['Situação']}  ·  Prazo: {r['Prazo']}"):
            st.write(f"**Segmentação:** {r['Segmentação']}  |  **Prazo:** {r['Prazo']}")
            note=st.text_area('Observações',value=r['Observações'] or '',key=f"note_{r['id']}")
            if st.button('Salvar observação',key=f"save_{r['id']}"):
                execute('UPDATE instances SET notes=? WHERE id=?',(note,int(r['id'])));st.success('Observação salva.')
            if r['Status']=='Pendente':
                if st.button('✓ Marcar como concluída',key=f"done_{r['id']}",type='primary'):
                    new='Aguardando aprovação' if r['Exige_aprovação'] else 'Concluída'
                    execute('UPDATE instances SET status=?,completed_at=?,completed_by=?,notes=? WHERE id=?',(new,datetime.now().isoformat(timespec='seconds'),user['id'],note,int(r['id'])));st.rerun()
            elif r['Status'] in ('Concluída','Aguardando aprovação'):
                if st.button('↩ Reabrir atividade',key=f"reopen_{r['id']}"):
                    execute("UPDATE instances SET status='Pendente',completed_at=NULL,completed_by=NULL,approved_at=NULL,approved_by=NULL WHERE id=?",(int(r['id']),));st.rerun()

elif page.startswith('📋'):
    if df.empty:st.info('Nenhuma atividade neste período.')
    else:
        st.dataframe(df[['Atividade','Segmentação','Responsável','Prazo','Situação','Conclusão','Observações']],hide_index=True,use_container_width=True)
        pending=df[df['Status']=='Aguardando aprovação']
        st.subheader('Aguardando aprovação')
        if pending.empty:st.success('Não há aprovações pendentes.')
        for _,r in pending.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Atividade']}** — {r['Responsável']} — {r['Segmentação']}")
                st.caption(r['Observações'] or 'Sem observações')
                a,b=st.columns(2)
                if a.button('✓ Aprovar',key=f"approve_{r['id']}"):
                    execute("UPDATE instances SET status='Aprovada',approved_at=?,approved_by=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),user['id'],int(r['id'])));st.rerun()
                if b.button('↩ Devolver',key=f"reject_{r['id']}"):
                    execute("UPDATE instances SET status='Pendente',completed_at=NULL,completed_by=NULL WHERE id=?",(int(r['id']),));st.rerun()
        st.subheader('Lançar atividade avulsa neste mês')
        tasks=rows('SELECT t.id,t.title,u.name AS owner FROM tasks t JOIN users u ON t.assignee_id=u.id WHERE t.active=1')
        if tasks:
            chosen=st.selectbox('Atividade cadastrada',tasks,format_func=lambda x:f"{x['title']} · {x['owner']}")
            if st.button('Gerar para o mês selecionado'):
                t=rows('SELECT * FROM tasks WHERE id=?',(chosen['id'],))[0]
                year,month=map(int,period.split('-'))
                execute('INSERT OR IGNORE INTO instances(task_id,period,due_date) VALUES(?,?,?)',(t['id'],period,due_date(year,month,t['due_day'],t['working_day']).isoformat()));st.rerun()

elif page.startswith('⚙'):
    tab1, tab2, tab3, tab4 = st.tabs(['Atividades', 'Usuários', 'Segmentações', 'Licenças'])

    with tab1:
        users = [dict(u) for u in rows(
            'SELECT id,name FROM users WHERE active=1 ORDER BY name'
        )]

        segs = [dict(s) for s in rows(
            'SELECT id,name FROM segments ORDER BY name'
        )]
        tasks=rows('SELECT t.*,s.name AS segment,u.name AS owner FROM tasks t JOIN segments s ON t.segment_id=s.id JOIN users u ON t.assignee_id=u.id ORDER BY t.id DESC')
        choices={'➕ Nova atividade':None,**{f"#{t['id']} · {t['title']}":t for t in tasks}}
        selected=st.selectbox('Criar ou editar',list(choices))
        item=choices[selected]
       
        with st.form('task_form'):
            title = st.text_input('Atividade', value=item['title'] if item else '')

            segment_index = next(
                (i for i, s in enumerate(segs) if item and s['id'] == item['segment_id']),
                0
            )

            segment = st.selectbox(
                'Segmentação',
                segs,
                index=segment_index,
                format_func=lambda x: x['name']
            )

            assignee_index = next(
                (i for i, u in enumerate(users) if item and u['id'] == item['assignee_id']),
                0
            )

            assignee = st.selectbox(
                'Responsável',
                users,
                index=assignee_index,
                format_func=lambda x: x['name']
            )

            due=st.number_input('Dia do vencimento',1,31,value=item['due_day'] if item else 10)
            working=st.checkbox('Contar como dia útil (segunda a sexta, sem feriados)',value=bool(item['working_day']) if item else False)
            recurring=st.checkbox('Repetir mensalmente',value=bool(item['recurring']) if item else True)
            approval=st.checkbox('Exigir aprovação do coordenador',value=bool(item['requires_approval']) if item else False)
            active=st.checkbox('Atividade ativa',value=bool(item['active']) if item else True)
            description=st.text_area('Instruções / descrição',value=item['description'] if item else '')
            if st.form_submit_button('Salvar atividade',type='primary'):
                if not title.strip():st.error('Informe o nome da atividade.')
                elif item:
                    execute('UPDATE tasks SET title=?,segment_id=?,assignee_id=?,due_day=?,working_day=?,recurring=?,requires_approval=?,active=?,description=? WHERE id=?',(title.strip(),segment['id'],assignee['id'],due,int(working),int(recurring),int(approval),int(active),description,item['id']))
                    st.success('Atividade atualizada. Alterações de prazo não mudam meses já gerados.')
                else:
                    execute('INSERT INTO tasks(title,segment_id,assignee_id,due_day,working_day,recurring,requires_approval,active,description) VALUES(?,?,?,?,?,?,?,?,?)',(title.strip(),segment['id'],assignee['id'],due,int(working),int(recurring),int(approval),int(active),description))
                    st.success('Atividade cadastrada! Abra o mês no Dashboard para gerar a recorrência.');st.rerun()
        st.dataframe(pd.DataFrame([{'ID':t['id'],'Atividade':t['title'],'Segmentação':t['segment'],'Responsável':t['owner'],'Ativa':bool(t['active'])} for t in tasks]),hide_index=True,use_container_width=True)
    with tab2:
        with st.form('new_user'):
            name=st.text_input('Nome completo')
            login=st.text_input('Nome de usuário')
            pw=st.text_input('Senha inicial',type='password')
            role=st.selectbox('Perfil',['colaborador','coordenador','admin'])
            if st.form_submit_button('Criar usuário'):
                if not name.strip() or not login.strip() or len(pw)<10:st.error('Informe nome, usuário e senha com pelo menos 10 caracteres.')
                else:
                    try:execute('INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)',(name.strip(),login.strip(),hash_pw(pw),role));st.success('Usuário criado.')
                    except sqlite3.IntegrityError:st.error('Nome de usuário já utilizado.')
        users_all=rows('SELECT id,name,username,role,active FROM users ORDER BY name')
        st.dataframe(pd.DataFrame([dict(x) for x in users_all]),hide_index=True,use_container_width=True)
       
        with st.form('edit_user'):
            target = st.selectbox(
                'Editar usuário',
                [dict(u) for u in users_all],
                format_func=lambda x: f"{x['name']} ({x['username']})"
            )
            newrole = st.selectbox('Perfil', ['colaborador', 'coordenador', 'admin'], index=['colaborador', 'coordenador', 'admin'].index(target['role']))
            newpw=st.text_input('Nova senha (deixe vazio para manter)',type='password')
            active=st.checkbox('Ativo',value=bool(target['active']))
            if st.form_submit_button('Atualizar usuário'):
                if newpw and len(newpw)<10:st.error('Senha deve ter pelo menos 10 caracteres.')
                elif target['id']==user['id'] and (not active or newrole!='admin'):st.error('Não é permitido desativar ou remover o próprio perfil de administrador.')
                else:
                    execute('UPDATE users SET role=?,active=? WHERE id=?',(newrole,int(active),target['id']))
                    if newpw:execute('UPDATE users SET password=? WHERE id=?',(hash_pw(newpw),target['id']))
                    st.success('Usuário atualizado.');st.rerun()
    with tab3:
        st.dataframe(q('SELECT * FROM segments ORDER BY name'),hide_index=True,use_container_width=True)
        with st.form('new_seg'):
            newseg=st.text_input('Nome da nova segmentação')
            if st.form_submit_button('Adicionar segmentação'):
                try:execute('INSERT INTO segments(name) VALUES(?)',(newseg.strip(),));st.success('Segmentação criada.');st.rerun()
                except sqlite3.IntegrityError:st.error('Segmentação já existe.')
        with st.form('edit_seg'):
            seglist=rows('SELECT * FROM segments ORDER BY name')
            
            old = st.selectbox(
                'Renomear segmentação',
                [dict(s) for s in seglist],
                format_func=lambda x: x['name']
            )
            newname = st.text_input('Novo nome')

            if st.form_submit_button('Renomear') and newname.strip():
                try:execute('UPDATE segments SET name=? WHERE id=?',(newname.strip(),old['id']));st.success('Segmentação renomeada.');st.rerun()
                except sqlite3.IntegrityError:st.error('Já existe segmentação com esse nome.')

    with tab4:
        st.subheader('Filiais / Unidades')
        with st.form('new_branch', clear_on_submit=True):
            new_branch = st.text_input('Nome da filial')
            if st.form_submit_button('Cadastrar filial'):
                if not new_branch.strip():
                    st.error('Informe o nome da filial.')
                else:
                    try:
                        execute('INSERT INTO branches(name) VALUES(?)', (new_branch.strip(),))
                        st.success('Filial cadastrada.'); st.rerun()
                    except sqlite3.IntegrityError:
                        st.error('Esta filial já está cadastrada.')
        branches = [dict(x) for x in rows('SELECT id,name FROM branches WHERE active=1 ORDER BY name')]
        st.subheader('Cadastro e renovação de licenças')
        if not branches:
            st.info('Cadastre ao menos uma filial antes de cadastrar licenças.')
        else:
            license_list = [dict(x) for x in rows('SELECT * FROM licenses ORDER BY name')]
            opts = {'➕ Nova licença':None, **{f"#{x['id']} · {x['name']}":x for x in license_list}}
            selected = st.selectbox('Criar ou editar licença', list(opts))
            current = opts[selected]
            users_for_license = [dict(x) for x in rows('SELECT id,name FROM users WHERE active=1 ORDER BY name')]
            with st.form('license_form'):
                license_name = st.text_input('Licença / Alvará', value=current['name'] if current else '')
                branch_idx = next((i for i,b in enumerate(branches) if current and b['id']==current['branch_id']),0)
                chosen_branch = st.selectbox('Filial', branches, index=branch_idx, format_func=lambda x:x['name'])
                issuer = st.text_input('Órgão emissor', value=current['issuer'] or '' if current else '')
                number = st.text_input('Número do documento', value=current['document_number'] or '' if current else '')
                issue_date = st.date_input('Data de emissão', value=date.fromisoformat(current['issued_on']) if current and current['issued_on'] else None)
                expiry_date = st.date_input('Vencimento', value=date.fromisoformat(current['expires_on']) if current else date.today())
                user_options = [None] + users_for_license
                owner_idx = next((i for i,u in enumerate(user_options) if u and current and u['id']==current['responsible_id']),0)
                owner = st.selectbox('Responsável', user_options, index=owner_idx, format_func=lambda x:x['name'] if x else 'Não definido')
                notes = st.text_area('Observações', value=current['notes'] or '' if current else '')
                active_license = st.checkbox('Licença ativa', value=bool(current['active']) if current else True)
                if st.form_submit_button('Salvar licença', type='primary'):
                    if not license_name.strip():
                        st.error('Informe o nome da licença.')
                    elif current:
                        if current['expires_on'] != expiry_date.isoformat():
                            execute('INSERT INTO license_renewals(license_id,old_expires_on,new_expires_on,renewed_by) VALUES(?,?,?,?)',
                                    (current['id'], current['expires_on'], expiry_date.isoformat(), user['id']))
                        execute('''UPDATE licenses SET name=?,branch_id=?,issuer=?,document_number=?,issued_on=?,
                                expires_on=?,responsible_id=?,notes=?,active=? WHERE id=?''',
                                (license_name.strip(),chosen_branch['id'],issuer,number,issue_date.isoformat() if issue_date else None,
                                 expiry_date.isoformat(),owner['id'] if owner else None,notes,int(active_license),current['id']))
                        st.success('Licença atualizada.'); st.rerun()
                    else:
                        execute('''INSERT INTO licenses(name,branch_id,issuer,document_number,issued_on,expires_on,responsible_id,notes,active)
                                VALUES(?,?,?,?,?,?,?,?,?)''',
                                (license_name.strip(),chosen_branch['id'],issuer,number,issue_date.isoformat() if issue_date else None,
                                 expiry_date.isoformat(),owner['id'] if owner else None,notes,int(active_license)))
                        st.success('Licença cadastrada.'); st.rerun()
            st.subheader('Histórico de alterações de vencimento')
            renewals = q('''SELECT l.name AS Licença, b.name AS Filial, r.old_expires_on AS Vencimento_anterior,
                r.new_expires_on AS Novo_vencimento, r.renewed_at AS Alterado_em, u.name AS Alterado_por
                FROM license_renewals r JOIN licenses l ON r.license_id=l.id
                JOIN branches b ON l.branch_id=b.id
                LEFT JOIN users u ON r.renewed_by=u.id ORDER BY r.renewed_at DESC''')
            st.dataframe(renewals, hide_index=True, use_container_width=True)

elif page.startswith('🔒'):
    with st.form('password'):
        old=st.text_input('Senha atual',type='password')
        new=st.text_input('Nova senha (mínimo 10 caracteres)',type='password')
        confirm=st.text_input('Confirmar nova senha',type='password')
        if st.form_submit_button('Alterar senha'):
            if not verify_pw(old,user['password']):st.error('Senha atual incorreta.')
            elif len(new)<10:st.error('A nova senha precisa ter ao menos 10 caracteres.')
            elif new!=confirm:st.error('As senhas não coincidem.')
            else:execute('UPDATE users SET password=? WHERE id=?',(hash_pw(new),user['id']));st.success('Senha alterada.')

st.caption('Grupo TLOG · Sistema interno de atividades · Versão inicial | Dias úteis não consideram feriados. Utilize HTTPS e hospedagem com backup para uso em produção.')
