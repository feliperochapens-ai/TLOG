import os, sqlite3, hashlib, hmac, secrets, calendar
from datetime import date, datetime, timedelta
from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st

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
    pages=['📊 Dashboard','☑️ Minhas atividades']+(['📋 Equipe e aprovações'] if manager else [])+(['⚙️ Administração'] if admin else [])+['🔒 Minha senha']
    page=st.radio('Navegação',pages,label_visibility='collapsed')
    st.divider()
    if st.button('Sair',use_container_width=True):
        st.session_state.pop('user_id',None);st.rerun()

st.markdown('<div class="tlog-head"><b>☰ &nbsp; G R U P O &nbsp; TLOG</b><b>Gestão de Atividades</b><small>'+user['name']+'</small></div>',unsafe_allow_html=True)
st.markdown('<div class="tlog-banner"><h2>'+page[2:]+'</h2><p>Acompanhe e organize as atividades mensais da equipe.</p></div>',unsafe_allow_html=True)

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

if page.startswith('📊'):
    if df.empty:st.info('Nenhuma atividade cadastrada para este mês.');st.stop()
    a,b,c=st.columns([2,2,2])
    with a: seg=st.multiselect('Segmentação',sorted(df['Segmentação'].unique()))
    with b: people=st.multiselect('Responsável',sorted(df['Responsável'].unique()))
    with c: statuses=st.multiselect('Situação',sorted(df['Situação'].unique()))
    view=df.copy()
    if seg:view=view[view['Segmentação'].isin(seg)]
    if people:view=view[view['Responsável'].isin(people)]
    if statuses:view=view[view['Situação'].isin(statuses)]
    counts=view['Situação'].value_counts();total=len(view);done=int(counts.get('Concluída',0)+counts.get('Aprovada',0));pending=int(counts.get('Pendente',0)+counts.get('Aguardando aprovação',0));late=int(counts.get('Atrasada',0))
    cols=st.columns(4)
    for col,(label,value,color) in zip(cols,[('Atividades previstas',total,'#3766d6'),('Concluídas / aprovadas',done,'#159d6d'),('Pendentes / em aprovação',pending,'#dfa224'),('Atrasadas',late,'#df4a59')]):
        col.markdown(f'<div class="metric" style="--accent:{color}"><div class="label">{label}</div><div class="value">{value}</div></div>',unsafe_allow_html=True)
    st.write('');st.progress(done/total if total else 0,text=f'Progresso de conclusão: {done}/{total} ({done/total:.0%})' if total else 'Sem atividades')
    left,right=st.columns(2)
    if not view.empty:
        with left:
            group=view.groupby(['Segmentação','Situação']).size().reset_index(name='Quantidade')
            fig=px.bar(group,x='Segmentação',y='Quantidade',color='Situação',barmode='stack',title='Atividades por segmentação',color_discrete_map={'Concluída':'#19a474','Aprovada':'#168f66','Pendente':'#e8b247','Aguardando aprovação':'#6385eb','Atrasada':'#e0525d'})
            fig.update_layout(xaxis_title='',legend_title='',margin=dict(t=45,b=20));st.plotly_chart(fig,use_container_width=True)
        with right:
            group=view.groupby('Situação').size().reset_index(name='Quantidade')
            fig=px.pie(group,names='Situação',values='Quantidade',hole=.6,title='Distribuição das atividades',color='Situação',color_discrete_map={'Concluída':'#19a474','Aprovada':'#168f66','Pendente':'#e8b247','Aguardando aprovação':'#6385eb','Atrasada':'#e0525d'})
            st.plotly_chart(fig,use_container_width=True)
    history=q('''SELECT i.period,s.name AS Segmentação,i.status,COUNT(*) AS quantidade FROM instances i JOIN tasks t ON i.task_id=t.id JOIN segments s ON t.segment_id=s.id JOIN users u ON t.assignee_id=u.id WHERE i.period<=? AND i.period>=? '''+('AND t.assignee_id=? ' if not manager else '')+''' GROUP BY i.period,s.name,i.status''',(period,(date.fromisoformat(period+'-01')-timedelta(days=180)).strftime('%Y-%m'),user['id']) if not manager else (period,(date.fromisoformat(period+'-01')-timedelta(days=180)).strftime('%Y-%m')))
    if not history.empty:
        history['ok']=history['status'].isin(['Concluída','Aprovada'])
        h=history.groupby(['period','Segmentação','ok'])['quantidade'].sum().unstack(fill_value=0).reset_index()
        h['Conclusão (%)']=(100*h.get(True,0)/(h.get(True,0)+h.get(False,0))).round(1)
        fig=px.line(h,x='period',y='Conclusão (%)',color='Segmentação',markers=True,title='Evolução histórica por segmentação',range_y=[0,100]);st.plotly_chart(fig,use_container_width=True)
    st.subheader('Detalhamento')
    cols=['Atividade','Segmentação','Responsável','Prazo','Situação','Conclusão','Observações']
    st.dataframe(view[cols],hide_index=True,use_container_width=True)
    st.download_button('⬇ Exportar Excel',excel_bytes(view[cols]),file_name=f'TLOG_atividades_{period}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

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
    tab1, tab2, tab3 = st.tabs(['Atividades', 'Usuários', 'Segmentações'])

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
