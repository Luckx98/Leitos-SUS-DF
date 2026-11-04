# Painel

O painel é o serviço `painel`, Streamlit na porta 8501. Ele lê só o schema `consumo`.

Três blocos, os da pergunta da E1:

- a série da ocupação por região de saúde, com a linha em 85%;
- as semanas em que a ocupação passou de 85%, com a marca provisória ou madura;
- os capítulos da CID-10 que concentravam o paciente-dia nessas semanas.

O seletor de UF abre o Distrito Federal e, no mesmo recorte da carga, Goiás. O seletor de região restringe os três blocos.

Na amostra (uma competência, sem rede) o painel avisa que a série de 2021 a 2025 sobe com `MODO=completo`. Se nenhuma semana do recorte passou de 85%, a resposta é essa: não há excesso para abrir por causa.

A página deixa escrito que lê o ouro (`consumo`), não a origem. As comparações ficam fora do painel:

- **Ouro contra a origem.** `sql/e3/opcao_nula.sql` recalcula a pergunta na origem, com o cadastro mais recente (a L4). O painel usa a versão do estabelecimento vigente no mês da saída.
- **Bronze contra bronze.** `lakehouse/reconciliar.py`, no perfil `e2`, compara origem, `lote.*` e `cdc.*`.
- **Ouro contra ele mesmo no tempo.** `consumo.controle_freshness` e a marca provisória da semana, que o painel já mostra.

```bash
docker compose --profile e3 up --build
# http://localhost:8501
```
