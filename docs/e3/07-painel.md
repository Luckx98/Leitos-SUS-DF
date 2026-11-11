# Painel

O painel é o serviço `painel`, Streamlit na porta 8501. Ele lê só o schema `consumo`.

Três blocos, os da pergunta da E1:

- a série da ocupação por região de saúde, com a linha em 85%;
- as semanas em que a ocupação passou de 85%, com a marca provisória ou madura;
- os capítulos da CID-10 que concentravam o paciente-dia nessas semanas.

O seletor de UF abre o Distrito Federal e, no mesmo recorte da carga, Goiás. O seletor de região restringe os três blocos.

Na amostra (uma competência, sem rede) o painel avisa que a série de 2021 a 2025 sobe com `MODO=completo`. Se nenhuma semana do recorte passou de 85%, a resposta é essa: não há excesso para abrir por causa.

```bash
docker compose --profile e3 up --build
# http://localhost:8501
```
