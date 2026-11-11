"""Gera a apresentação da entrega 3 (camada analítica) em PPTX.

Uso:
    python3 -m pip install python-pptx
    python3 apresentacao/gerar_slides.py
"""

from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

W = 13.333
H = 7.5
ML = 0.42
CW = 12.49

INK = RGBColor(0x1C, 0x19, 0x17)
MUTED = RGBColor(0x57, 0x53, 0x4E)
ACCENT = RGBColor(0x0F, 0x51, 0x32)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SURFACE = RGBColor(0xF5, 0xF4, 0xF1)
LINE = RGBColor(0xE7, 0xE5, 0xE4)
SOFT = RGBColor(0xE8, 0xF2, 0xEC)
WARN_BG = RGBColor(0xFB, 0xF3, 0xE4)
WARN = RGBColor(0x92, 0x40, 0x0E)
HEADER_BG = RGBColor(0x1C, 0x19, 0x17)
ROW_ALT = RGBColor(0xFA, 0xF9, 0xF7)

FONT = "Calibri"
TOTAL = 4
OUT = "apresentacao/leitos-sus-df-e3.pptx"


def _anchor(tf, anchor: MSO_ANCHOR) -> None:
    value = {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor]
    tf._txBody.bodyPr.set("anchor", value)


def _no_autofit(tf) -> None:
    body = tf._txBody.bodyPr
    for child in list(body):
        if child.tag.endswith("spAutoFit") or child.tag.endswith("normAutofit"):
            body.remove(child)
    if body.find(qn("a:noAutofit")) is None:
        body.append(body.makeelement(qn("a:noAutofit"), {}))


def add_rect(slide, x, y, w, h, fill):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    return shape


def add_text(
    slide,
    text,
    x,
    y,
    w,
    h,
    *,
    size=16,
    bold=False,
    color=INK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    spacing=1.0,
):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = True
    _no_autofit(tf)
    _anchor(tf, anchor)
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    p.line_spacing = spacing
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    return shape


def add_runs(slide, runs, x, y, w, h, *, spacing=1.02):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.word_wrap = True
    _no_autofit(tf)
    _anchor(tf, MSO_ANCHOR.TOP)
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    for i, parts in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.space_before = Pt(0)
        p.space_after = Pt(5)
        p.line_spacing = spacing
        for text, size, bold, color in parts:
            run = p.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            run.font.name = FONT
    return shape


def footer(slide, page):
    add_rect(slide, ML, 7.18, CW, 0.01, LINE)
    add_text(
        slide,
        "Leitos SUS-DF   ·   Entrega 3   ·   Grupo 01",
        ML,
        7.22,
        8,
        0.22,
        size=11,
        color=MUTED,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    add_text(
        slide,
        f"{page}  /  {TOTAL}",
        10.4,
        7.22,
        2.5,
        0.22,
        size=11,
        color=MUTED,
        align=PP_ALIGN.RIGHT,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def chrome(slide, kicker, title, page):
    add_rect(slide, 0, 0, W, 0.08, ACCENT)
    add_text(slide, kicker, ML, 0.2, CW, 0.24, size=11, bold=True, color=ACCENT)
    add_text(slide, title, ML, 0.46, CW, 0.46, size=26, bold=True)
    footer(slide, page)


def add_table(slide, headers, rows, x, y, w, h, col_widths, font=13):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(w), Inches(h))
    table = shape.table
    for i, width in enumerate(col_widths):
        table.columns[i].width = Inches(width)

    def paint(cell, text, fill, color, bold):
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        cell.margin_left = Inches(0.08)
        cell.margin_right = Inches(0.08)
        cell.margin_top = Inches(0.05)
        cell.margin_bottom = Inches(0.05)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = FONT

    for i, header in enumerate(headers):
        paint(table.cell(0, i), header, HEADER_BG, WHITE, True)
    for r, row in enumerate(rows):
        fill = ROW_ALT if r % 2 else WHITE
        for c, value in enumerate(row):
            paint(table.cell(r + 1, c), value, fill, INK, False)
    return shape


def stat(slide, x, y, w, h, value, label):
    add_rect(slide, x, y, w, h, SURFACE)
    add_rect(slide, x, y, 0.06, h, ACCENT)
    add_text(slide, value, x + 0.18, y + 0.08, w - 0.28, 0.38, size=20, bold=True, color=INK)
    add_text(slide, label, x + 0.18, y + 0.46, w - 0.28, 0.38, size=11, color=MUTED)


def slide_e3(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(slide, 0, 0, W, 0.08, ACCENT)
    add_text(
        slide,
        "ENTREGA 3   ·   CAMADA ANALÍTICA   ·   GRUPO 01   ·   BD2 UNB/FCTE 2026/2",
        ML,
        0.2,
        CW,
        0.24,
        size=11,
        bold=True,
        color=ACCENT,
    )
    add_text(
        slide,
        "A semana em que a ocupação passa de 85%",
        ML,
        0.44,
        CW,
        0.42,
        size=28,
        bold=True,
    )
    add_rect(slide, ML, 0.96, CW, 0.72, SOFT)
    add_rect(slide, ML, 0.96, 0.07, 0.72, ACCENT)
    add_text(
        slide,
        "Pergunta.  Entre 2021 e 2025, em quais semanas a ocupação (paciente-dia ÷ leitos SUS × 7) "
        "ultrapassou 85% em cada região de saúde do DF, e quais capítulos da CID concentravam esse excesso?",
        ML + 0.22,
        1.08,
        CW - 0.36,
        0.5,
        size=14,
        color=INK,
        spacing=1.05,
    )

    stats = [
        ("77", "Passos do dbt build, sem erro"),
        ("6,5 s", "Build da amostra no perfil e3"),
        ("28", "Semanas publicadas na amostra"),
        ("0", "Semanas acima de 85% nesse mês"),
    ]
    gap = 0.14
    width = (CW - 3 * gap) / 4
    for i, (value, label) in enumerate(stats):
        stat(slide, ML + i * (width + gap), 1.84, width, 0.9, value, label)

    col_w = (CW - 0.28) / 2
    add_text(slide, "O que propomos", ML, 2.9, col_w, 0.28, size=15, bold=True)
    add_runs(
        slide,
        [
            [("Estrela no grão da semana: uma região de saúde numa semana ISO, com paciente-dia, leitos SUS, ocupação e a coluna acima de 85%.", 13, False, INK)],
            [("A causa abre essa semana pelo capítulo da CID-10. O paciente-dia fica na transformação e não é publicado.", 13, False, INK)],
            [("O estabelecimento é variação lenta tipo 2, ligado à versão vigente no mês da saída.", 13, False, INK)],
            [("dbt em três camadas sobre o lote, publicado no schema consumo. Dagster às 06:00, com retry, backfill por ano e SLA de 24 h.", 13, False, INK)],
            [("O painel (porta 8501) lê só o consumo: a série, as semanas acima do limiar e os capítulos da CID.", 13, False, INK)],
        ],
        ML,
        3.24,
        col_w,
        2.35,
    )
    add_text(slide, "O que já roda na amostra", ML + col_w + 0.28, 2.9, col_w, 0.28, size=15, bold=True)
    add_runs(
        slide,
        [
            [("DF, janeiro de 2025, sem rede: 20.995 internações e 122.450 paciente-dias. Nenhuma semana passou de 85%.", 13, False, INK)],
            [("A opção nula, o mesmo cálculo direto na origem, levou 1,0 s. Ler o mart no Postgres levou 11,8 ms.", 13, False, INK)],
            [("O plano de fato_internacao saiu de varredura (2,51 ms) para índice (1,16 ms).", 13, False, INK)],
            [("O retry conclui na segunda tentativa. O backfill de um ano devolve as linhas daquele ano e preserva os outros.", 13, False, INK)],
            [("O pgvector guarda a frase de cada semana. A ordenação por cosseno não substitui a coluna acima de 85%.", 13, False, INK)],
        ],
        ML + col_w + 0.28,
        3.24,
        col_w,
        2.35,
    )

    note_w = (CW - 0.16) / 2
    add_rect(slide, ML, 5.72, note_w, 1.12, WARN_BG)
    add_text(slide, "Série de cinco anos", ML + 0.16, 5.84, note_w - 0.3, 0.26, size=13, bold=True, color=WARN)
    add_text(
        slide,
        "MODO=completo publicou DF e GO: 7.500 semanas e 207 acima de 85%. O build levou 21,4 s. Ler o excesso no Postgres levou 41,8 ms.",
        ML + 0.16,
        6.14,
        note_w - 0.32,
        0.58,
        size=12,
        color=INK,
    )
    add_rect(slide, ML + note_w + 0.16, 5.72, note_w, 1.12, SURFACE)
    add_text(
        slide,
        "Como reproduzir",
        ML + note_w + 0.32,
        5.84,
        note_w - 0.3,
        0.26,
        size=13,
        bold=True,
    )
    add_text(
        slide,
        "docker compose --profile e3 up --build. Painel em localhost:8501, Dagster em localhost:3000. Decisões no ADR 0003 e no ADR 0004.",
        ML + note_w + 0.32,
        6.14,
        note_w - 0.32,
        0.58,
        size=12,
        color=INK,
    )
    footer(slide, 1)


def slide_bases(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, "ENTREGA 3  ·  BASES", "Três bases, um fluxo", 2)
    add_text(
        slide,
        "O dbt transforma no DuckDB. O PostgreSQL guarda a origem, o catálogo do Iceberg e o que o painel consulta. "
        "O lote fica em Iceberg, no SeaweedFS, e entra na transformação pelo snapshot atual.",
        ML,
        1.1,
        CW,
        0.62,
        size=15,
        color=MUTED,
    )
    add_table(
        slide,
        ["Base", "Onde mora", "O que a entrega 3 usa"],
        [
            ["PostgreSQL 16", "public, consumo, semantico", "Referências, mart publicado e o vetor"],
            ["DuckDB", "bronze, staging, intermediate, marts", "Motor do dbt, da bronze ao ouro"],
            ["Iceberg", "lote.* no SeaweedFS (S3)", "Snapshot que a bronze lê, sem copiar o arquivo"],
        ],
        ML,
        1.9,
        CW,
        2.15,
        [2.4, 4.7, 5.39],
        font=14,
    )
    add_text(slide, "O que cada uma não faz", ML, 4.3, CW, 0.3, size=15, bold=True)
    add_runs(
        slide,
        [
            [("O painel não abre Iceberg nem DuckDB. A série, o excesso de 85% e os capítulos da CID saem do schema consumo.", 14, False, INK)],
            [("As referências (CID, município, região de saúde e a região curada do DF) não foram para o lakehouse. O DuckDB as copia do PostgreSQL para a bronze.", 14, False, INK)],
            [("O perfil e3 não sobe o CDC. A camada analítica lê o lote, o caminho que reprocessa a internação que chega meses depois.", 14, False, INK)],
        ],
        ML,
        4.68,
        CW,
        1.7,
        spacing=1.05,
    )


def slide_postgres(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, "ENTREGA 3  ·  POSTGRESQL", "Um servidor, quatro papéis", 3)
    add_text(
        slide,
        "A imagem é pgvector/pgvector:pg16. A extensão vector mora no mesmo servidor da origem. O número da ocupação continua no warehouse.",
        ML,
        1.1,
        CW,
        0.4,
        size=15,
        color=MUTED,
    )
    stats = [
        ("3,80 mi", "Internações em fato_internacao"),
        ("7.500", "Semanas por região, DF e GO"),
        ("207", "Semanas com ocupação acima de 85%"),
        ("41,8 ms", "Ler esse excesso no PostgreSQL"),
    ]
    gap = 0.14
    width = (CW - 3 * gap) / 4
    for i, (value, label) in enumerate(stats):
        stat(slide, ML + i * (width + gap), 1.62, width, 0.92, value, label)

    add_table(
        slide,
        ["Papel", "O que guarda"],
        [
            ["public", "Origem: internação, leito, versão de cadastro, CID, município e região"],
            ["catálogo Iceberg", "Metadado SQL do lote. O dbt acha o snapshot pelo metadata_location"],
            ["consumo", "Dimensões, fatos, SLA e freshness. Índices e o plano do EXPLAIN ficam aqui"],
            ["semantico", "Frase da semana e embedding de 384 dimensões, com índice HNSW"],
        ],
        ML,
        2.78,
        CW,
        2.55,
        [2.5, 9.99],
        font=14,
    )
    add_text(
        slide,
        "Série DF e GO, 11/11/2026. A opção nula, a mesma conta direto na origem, levou 55,5 s e contou 206 semanas acima de 85%. "
        "O mart, com a versão do cadastro vigente no mês da saída, conta 207. Fonte: medicoes/e3/granularidade_2026-11-11.txt.",
        ML,
        5.55,
        CW,
        0.85,
        size=13,
        color=MUTED,
    )


def slide_camadas(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    chrome(slide, "ENTREGA 3  ·  CAMADAS", "Bronze, silver e gold", 4)
    add_text(
        slide,
        "Bronze já é o nome no DuckDB. Silver e gold são os papéis de staging/intermediate e de marts/consumo.",
        ML,
        1.08,
        CW,
        0.32,
        size=14,
        color=MUTED,
    )
    cards = [
        (
            "Bronze",
            "schema bronze",
            "Snapshot atual de lote.* em views iceberg_scan: carga, internação, leito, estabelecimento_versao e maturidade. "
            "CID, município, região de saúde e a região curada do DF entram como cópia do PostgreSQL. Ainda sem regra de negócio.",
        ),
        (
            "Silver",
            "staging e intermediate",
            "Staging é view: a AIH da carga vigente, tipos limpos e o instante de ingestão em timestamptz. "
            "Intermediate materializa a variação lenta, a versão do mês da saída, o leito por região e mês e a semana. "
            "O paciente-dia é view e não segue adiante.",
        ),
        (
            "Gold",
            "marts e consumo",
            "No DuckDB, o schema marts. A publicação copia para o PostgreSQL, schema consumo: quatro dimensões, "
            "fato_internacao, ocupacao_semana_regiao, causa_semana_regiao e sla. Painel e freshness leem só esta camada.",
        ),
    ]
    gap = 0.16
    card_w = (CW - 2 * gap) / 3
    for i, (nome, onde, texto) in enumerate(cards):
        x = ML + i * (card_w + gap)
        add_rect(slide, x, 1.52, card_w, 3.85, SURFACE)
        add_rect(slide, x, 1.52, card_w, 0.08, ACCENT)
        add_text(slide, nome, x + 0.18, 1.72, card_w - 0.36, 0.36, size=20, bold=True)
        add_text(slide, onde, x + 0.18, 2.12, card_w - 0.36, 0.28, size=13, bold=True, color=ACCENT)
        add_text(slide, texto, x + 0.18, 2.5, card_w - 0.36, 2.7, size=13, color=INK, spacing=1.05)
    add_text(
        slide,
        "O grafo diário, às 06:00, é lote conferido, marts, publicar consumo, freshness. O build da série fechou 77 passos em 21,4 s.",
        ML,
        5.55,
        CW,
        0.55,
        size=14,
        color=MUTED,
    )


def main() -> None:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    prs.core_properties.title = "Leitos SUS-DF — entrega 3"
    prs.core_properties.author = "Grupo 01 — Banco de Dados 2, UnB/FCTE"
    prs.core_properties.subject = "Camada analítica: bases, PostgreSQL e bronze, silver, gold"
    slide_e3(prs)
    slide_bases(prs)
    slide_postgres(prs)
    slide_camadas(prs)
    prs.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
