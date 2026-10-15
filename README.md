# Grupo TLOG — Gestão de Atividades

Aplicação web em **Python + Streamlit + SQLite**, com layout inspirado no exemplo fornecido. Inclui login, perfis, tarefas recorrentes, segmentações, gráficos, aprovação, histórico e exportação Excel.

## Como executar (Windows)

1. Instale o Python 3.11 ou superior.
2. Extraia o ZIP e abra o terminal na pasta `tlog_atividades`.
3. Execute:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

4. O navegador abrirá `http://localhost:8501`.
5. No primeiro acesso, o usuário é `admin`. A senha provisória aleatória aparece **somente na primeira execução**, na tela de login. Guarde-a e altere em **Minha senha**.

Opcionalmente, defina `TLOG_ADMIN_PASSWORD` antes da primeira execução para escolher a senha inicial. O banco `atividades.db` é criado automaticamente.

## Funcionalidades

- **Colaborador:** acompanha e conclui suas tarefas, insere observações, reabre entregas não aprovadas.
- **Coordenador:** visualiza toda a equipe, filtra dashboards e aprova/devolve atividades que exigem validação.
- **Administrador:** todas as funções acima e cadastro/edição de usuários, tarefas, segmentações e regras de recorrência.
- **Dashboard:** indicadores de concluídas, pendentes, atrasadas; gráficos por segmento, distribuição de status e evolução histórica; exportação Excel.
- **Recorrência:** tarefas mensais são geradas ao acessar o mês. Tarefas avulsas podem ser geradas pelo coordenador.

## Importante antes de implantar na empresa

- Esta é uma **primeira versão funcional**, não uma solução corporativa auditada. Teste antes de usar com dados reais.
- Para vários usuários simultâneos e produção, recomenda-se migrar de SQLite para PostgreSQL, usar HTTPS, hospedagem interna aprovada pela TI, backups automatizados, logs de auditoria e controles de acesso adequados.
- O cálculo de dia útil considera segunda a sexta, **não feriados**.
- Alterar uma tarefa não altera retroativamente os prazos já gerados; isso preserva o histórico. Alterar responsável/nome da tarefa altera sua exibição também nos meses anteriores.
- Os gráficos históricos mostram períodos já gerados no banco, não meses futuros não gerados.
- Não há envio automático de e-mails nem integração com sistemas internos nesta versão.
