"""
Aplicación web interactiva: Análisis de mortalidad en Colombia (2019)
Fuente: DANE - Estadísticas Vitales (EEVV) 2019, defunciones no fetales.

Ejecutar localmente:
    python app.py            -> http://127.0.0.1:8050
En producción (Render):
    gunicorn app:server
"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, ctx

BASE = Path(__file__).resolve().parent
PROC = BASE / "data" / "processed"
RAW = BASE / "data" / "raw"

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
defun = pd.read_csv(PROC / "defunciones_2019.csv.gz",
                    dtype={"COD_DANE": str, "COD_DEPARTAMENTO": str, "COD_MUNICIPIO": str,
                           "COD_MUERTE": str, "MANERA_MUERTE": str})
divipola = pd.read_csv(PROC / "divipola.csv", dtype=str)
codigos = pd.read_csv(PROC / "codigos_muerte.csv", dtype=str)
with open(RAW / "colombia_departamentos.geojson", encoding="utf-8") as f:
    geo_dptos = json.load(f)

# Nombres de departamento y municipio
dptos = (divipola[["COD_DEPARTAMENTO", "DEPARTAMENTO"]].drop_duplicates()
         .set_index("COD_DEPARTAMENTO")["DEPARTAMENTO"])
# Nombres cortos para que las etiquetas de los ejes sean legibles
NOMBRE_CORTO = {
    "ARCHIPIÉLAGO DE SAN ANDRÉS, PROVIDENCIA Y SANTA CATALINA": "SAN ANDRÉS",
    "BOGOTÁ, D.C.": "BOGOTÁ D.C.",
}
dptos = dptos.replace(NOMBRE_CORTO)
mpios = divipola.set_index("COD_DANE")["MUNICIPIO"]

defun["DEPARTAMENTO"] = defun["COD_DEPARTAMENTO"].map(dptos).fillna("SIN INFORMACIÓN")
defun["MUNICIPIO"] = defun["COD_DANE"].map(mpios).fillna("SIN INFORMACIÓN")
def titulo(txt: str) -> str:
    """Pasa a formato título dejando en minúscula los conectores (de, del, la...)."""
    menores = {"De", "Del", "La", "Las", "Los", "Y", "El"}
    palabras = txt.title().split(" ")
    return " ".join(p.lower() if i > 0 and p in menores else p for i, p in enumerate(palabras))


def nombre_ciudad(mpio: str, dpto: str) -> str:
    if mpio.startswith("BOGOTÁ"):
        return "Bogotá D.C."
    return f"{titulo(mpio)} ({titulo(dpto)})"


pares = defun[["MUNICIPIO", "DEPARTAMENTO"]].drop_duplicates()
pares["CIUDAD"] = [nombre_ciudad(m, d) for m, d in zip(pares["MUNICIPIO"], pares["DEPARTAMENTO"])]
defun = defun.merge(pares, on=["MUNICIPIO", "DEPARTAMENTO"], how="left")
defun["SEXO_TXT"] = defun["SEXO"].map({1: "Hombre", 2: "Mujer", 3: "Indeterminado"})

# Descripción de la causa (CIE-10). Si el código viene a 4 caracteres se usa la
# descripción de 4; si viene a 3 caracteres se usa la descripción de 3.
desc4 = codigos.drop_duplicates("COD_4").set_index("COD_4")["DESC_4"]
desc3 = codigos.drop_duplicates("COD_3").set_index("COD_3")["DESC_3"]
defun["CAUSA"] = defun["COD_MUERTE"].map(desc4).fillna(defun["COD_MUERTE"].map(desc3)) \
    .fillna("Sin descripción")

# Ciclo de vida según GRUPO_EDAD1 (tabla de referencia de la actividad)
CICLO = [
    ("Mortalidad neonatal", "< 1 mes", range(0, 5)),
    ("Mortalidad infantil", "1 a 11 meses", range(5, 7)),
    ("Primera infancia", "1 a 4 años", range(7, 9)),
    ("Niñez", "5 a 14 años", range(9, 11)),
    ("Adolescencia", "15 a 19 años", range(11, 12)),
    ("Juventud", "20 a 29 años", range(12, 14)),
    ("Adultez temprana", "30 a 44 años", range(14, 17)),
    ("Adultez intermedia", "45 a 59 años", range(17, 20)),
    ("Vejez", "60 a 84 años", range(20, 25)),
    ("Longevidad / Centenarios", "85 a 100+ años", range(25, 29)),
    ("Edad desconocida", "Sin información", range(29, 30)),
]
mapa_ciclo = {c: f"{nom}<br>({rango})" for nom, rango, codes in CICLO for c in codes}
ORDEN_CICLO = [f"{nom}<br>({rango})" for nom, rango, _ in CICLO]
defun["CICLO_VIDA"] = defun["GRUPO_EDAD1"].map(mapa_ciclo)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
               "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
AZUL = "#1f4e79"
COLOR_SEXO = {"Hombre": "#2b6cb0", "Mujer": "#d53f8c", "Indeterminado": "#a0aec0"}
FUENTE = "Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
PLANTILLA = dict(
    font=dict(family=FUENTE, size=12, color="#2d3748"),
    paper_bgcolor="white", plot_bgcolor="white",
    margin=dict(l=10, r=10, t=60, b=10),
    title=dict(x=0.01, xanchor="left", font=dict(size=15, color=AZUL)),
    hoverlabel=dict(font_family=FUENTE),
    separators=",.",  # formato colombiano: 1.234,5
)


def estilizar(fig, **kw):
    fig.update_layout(**PLANTILLA)
    fig.update_layout(**kw)
    fig.update_xaxes(showgrid=False, linecolor="#cbd5e0")
    fig.update_yaxes(gridcolor="#edf2f7", linecolor="#cbd5e0")
    return fig


def fmt(n):
    return f"{n:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
def filtrar(departamentos, sexos, meses):
    d = defun
    if departamentos:
        d = d[d["COD_DEPARTAMENTO"].isin(departamentos)]
    if sexos:
        d = d[d["SEXO"].isin(sexos)]
    if meses:
        d = d[d["MES"].between(meses[0], meses[1])]
    return d


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def fig_mapa(d, seleccion):
    agg = (d.groupby(["COD_DEPARTAMENTO", "DEPARTAMENTO"]).size()
           .reset_index(name="Muertes"))
    agg = agg[agg["COD_DEPARTAMENTO"].isin(dptos.index)]
    fig = px.choropleth(
        agg, geojson=geo_dptos, locations="COD_DEPARTAMENTO",
        featureidkey="properties.DPTO_CCDGO", color="Muertes",
        color_continuous_scale="Reds", hover_name="DEPARTAMENTO",
        hover_data={"COD_DEPARTAMENTO": False, "Muertes": ":,.0f"},
        labels={"Muertes": "Total de muertes"},
    )
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    if seleccion:
        sel = agg[agg["COD_DEPARTAMENTO"].isin(seleccion)]
        fig.add_trace(go.Choropleth(
            geojson=geo_dptos, locations=sel["COD_DEPARTAMENTO"], z=[1] * len(sel),
            featureidkey="properties.DPTO_CCDGO", showscale=False, hoverinfo="skip",
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            marker_line_color="#1a202c", marker_line_width=2.5))
    return estilizar(fig, title="Distribución total de muertes por departamento (2019)",
                     height=560, coloraxis_colorbar=dict(title="Muertes", thickness=12),
                     margin=dict(l=0, r=0, t=50, b=0))


def fig_lineas(d):
    agg = d.groupby("MES").size().reindex(range(1, 13), fill_value=0).reset_index(name="Muertes")
    agg["Mes"] = [MESES[m - 1] for m in agg["MES"]]
    agg["MesLargo"] = [MESES_LARGO[m - 1] for m in agg["MES"]]
    prom = agg.loc[agg["Muertes"] > 0, "Muertes"].mean() if agg["Muertes"].sum() else 0
    fig = go.Figure(go.Scatter(
        x=agg["Mes"], y=agg["Muertes"], mode="lines+markers+text",
        line=dict(color=AZUL, width=3), marker=dict(size=8),
        text=[fmt(v) for v in agg["Muertes"]], textposition="top center",
        textfont=dict(size=10), customdata=agg["MesLargo"],
        hovertemplate="<b>%{customdata}</b><br>Muertes: %{y:,.0f}<extra></extra>",
        name="Muertes"))
    fig.add_hline(y=prom, line_dash="dot", line_color="#e53e3e",
                  annotation_text=f"Promedio mensual: {fmt(prom)}",
                  annotation_position="bottom right", annotation_font_color="#e53e3e")
    estilizar(fig, title="Total de muertes por mes en Colombia (2019)", height=420,
              showlegend=False)
    fig.update_xaxes(title="Mes de defunción")
    fig.update_yaxes(title="Número de muertes")
    return fig


def fig_violentas(d):
    h = d[d["COD_MUERTE"].str.startswith("X95")]
    agg = h.groupby("CIUDAD").size().nlargest(5).sort_values().reset_index(name="Homicidios")
    fig = px.bar(agg, x="Homicidios", y="CIUDAD", orientation="h", text="Homicidios",
                 color_discrete_sequence=["#c53030"],
                 labels={"CIUDAD": "Ciudad", "Homicidios": "Homicidios por arma de fuego"})
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>Homicidios (X95): %{x:,.0f}<extra></extra>")
    estilizar(fig, title="Top 5 ciudades más violentas: homicidios por arma de fuego (X95)",
              height=420)
    fig.update_xaxes(title="Número de homicidios (CIE-10 X950–X959)")
    fig.update_yaxes(title=None)
    return fig


def fig_menor_mortalidad(d):
    agg = (d[d["MUNICIPIO"] != "SIN INFORMACIÓN"].groupby("CIUDAD").size()
           .reset_index(name="Muertes").sort_values(["Muertes", "CIUDAD"]).head(10))
    fig = px.pie(agg, names="CIUDAD", values="Muertes", hole=0.35,
                 color_discrete_sequence=px.colors.qualitative.Set3)
    fig.update_traces(texttemplate="%{value} muerte(s)<br>%{percent}", textposition="inside",
                      hovertemplate="<b>%{label}</b><br>Muertes: %{value}<br>%{percent}<extra></extra>",
                      marker=dict(line=dict(color="white", width=1.5)))
    return estilizar(fig, title="10 ciudades con menor número de muertes (2019)", height=420,
                     legend=dict(title="Ciudad", font=dict(size=10)))


def tabla_causas(d):
    agg = (d.groupby(["COD_MUERTE", "CAUSA"]).size().reset_index(name="Total")
           .sort_values("Total", ascending=False).head(10))
    total = len(d) or 1
    agg.insert(0, "Puesto", range(1, len(agg) + 1))
    agg["% del total"] = (agg["Total"] / total * 100).round(2)
    return agg.rename(columns={"COD_MUERTE": "Código CIE-10", "CAUSA": "Causa de muerte"}) \
        .to_dict("records")


def fig_sexo_dpto(d):
    agg = d.groupby(["DEPARTAMENTO", "SEXO_TXT"]).size().reset_index(name="Muertes")
    orden = agg.groupby("DEPARTAMENTO")["Muertes"].sum().sort_values(ascending=False).index
    fig = px.bar(agg, x="DEPARTAMENTO", y="Muertes", color="SEXO_TXT",
                 category_orders={"DEPARTAMENTO": list(orden),
                                  "SEXO_TXT": ["Hombre", "Mujer", "Indeterminado"]},
                 color_discrete_map=COLOR_SEXO,
                 labels={"SEXO_TXT": "Sexo", "DEPARTAMENTO": "Departamento"})
    fig.update_traces(hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:,.0f}<extra></extra>")
    estilizar(fig, title="Total de muertes por sexo en cada departamento (2019)", height=520,
              barmode="stack", legend=dict(orientation="h", y=1.02, x=1, xanchor="right",
                                           yanchor="bottom", title="Sexo: "))
    fig.update_xaxes(title="Departamento", tickangle=-45)
    fig.update_yaxes(title="Número de muertes")
    return fig


def fig_histograma(d):
    agg = d.groupby("CICLO_VIDA").size().reindex(ORDEN_CICLO, fill_value=0) \
        .reset_index(name="Muertes")
    agg.columns = ["Ciclo de vida", "Muertes"]
    fig = px.bar(agg, x="Ciclo de vida", y="Muertes", text="Muertes",
                 color_discrete_sequence=["#2b6cb0"])
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False,
                      marker_line_color="white", marker_line_width=1,
                      hovertemplate="<b>%{x}</b><br>Muertes: %{y:,.0f}<extra></extra>")
    estilizar(fig, title="Distribución de muertes por ciclo de vida (GRUPO_EDAD1)", height=480,
              bargap=0.02)
    fig.update_xaxes(title="Grupo de edad (categoría y rango aproximado)", tickfont=dict(size=10))
    fig.update_yaxes(title="Número de muertes")
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app = Dash(__name__, title="Mortalidad en Colombia 2019")
server = app.server  # para gunicorn

opciones_dpto = [{"label": titulo(nom), "value": cod}
                 for cod, nom in sorted(dptos.items(), key=lambda x: x[1])]


def tarjeta(titulo, id_valor, nota=None):
    return html.Div(className="kpi", children=[
        html.Div(titulo, className="kpi-titulo"),
        html.Div(id=id_valor, className="kpi-valor"),
        html.Div(nota or "", className="kpi-nota"),
    ])


def panel(titulo_desc, contenido, ancho="mitad"):
    return html.Div(className=f"panel {ancho}", children=[
        contenido, html.P(titulo_desc, className="nota-grafico")])


app.layout = html.Div(className="contenedor", children=[
    html.Header(className="encabezado", children=[
        html.Div([
            html.H1("Mortalidad en Colombia · 2019"),
            html.P("Aplicación web interactiva con Plotly y Dash a partir de los microdatos de "
                   "Estadísticas Vitales (defunciones no fetales) del DANE."),
        ]),
    ]),

    html.Section(className="filtros", children=[
        html.Div(className="filtro", children=[
            html.Label("Departamento(s)"),
            dcc.Dropdown(id="f-dpto", options=opciones_dpto, multi=True,
                         placeholder="Todo el país (también puedes hacer clic en el mapa)"),
        ]),
        html.Div(className="filtro", children=[
            html.Label("Sexo"),
            dcc.Checklist(id="f-sexo", inline=True, className="checks",
                          options=[{"label": " Hombre", "value": 1},
                                   {"label": " Mujer", "value": 2},
                                   {"label": " Indeterminado", "value": 3}],
                          value=[1, 2, 3]),
        ]),
        html.Div(className="filtro ancho", children=[
            html.Label("Meses"),
            dcc.RangeSlider(id="f-mes", min=1, max=12, step=1, value=[1, 12],
                            marks={i + 1: m for i, m in enumerate(MESES)}),
        ]),
        html.Button("Restablecer filtros", id="btn-reset", className="boton"),
    ]),

    html.Section(className="kpis", children=[
        tarjeta("Total de muertes", "kpi-total"),
        tarjeta("Hombres", "kpi-hombres"),
        tarjeta("Mujeres", "kpi-mujeres"),
        tarjeta("Homicidios por arma de fuego (X95)", "kpi-x95"),
    ]),

    html.Section(className="grid", children=[
        panel("Mapa coroplético: cada departamento se colorea según el total de defunciones. "
              "Haz clic en un departamento para filtrar todo el tablero.",
              dcc.Graph(id="g-mapa", config={"displaylogo": False,
                                               # topojson base servido localmente (assets/)
                                               "topojsonURL": "/assets/topojson/"}), "mitad"),
        html.Div(className="panel mitad", children=[
            html.H3("10 principales causas de muerte", className="titulo-tabla"),
            dash_table.DataTable(
                id="t-causas",
                columns=[{"name": "#", "id": "Puesto"},
                         {"name": "Código CIE-10", "id": "Código CIE-10"},
                         {"name": "Causa de muerte", "id": "Causa de muerte"},
                         {"name": "Total de casos", "id": "Total", "type": "numeric",
                          "format": {"specifier": ",.0f", "locale": {"group": ".", "decimal": ","}}},
                         {"name": "% del total", "id": "% del total", "type": "numeric"}],
                style_as_list_view=True,
                style_header={"backgroundColor": AZUL, "color": "white", "fontWeight": "600",
                              "fontFamily": FUENTE, "whiteSpace": "normal"},
                style_cell={"fontFamily": FUENTE, "fontSize": 13, "padding": "8px",
                            "textAlign": "left", "whiteSpace": "normal", "height": "auto"},
                style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "right"}
                                        for c in ["Total", "% del total", "Puesto"]],
                style_data_conditional=[{"if": {"row_index": "odd"},
                                         "backgroundColor": "#f7fafc"}],
            ),
            html.P("Causas agrupadas por código CIE-10 (DANE), ordenadas de mayor a menor número "
                   "de casos.", className="nota-grafico"),
        ]),
        panel("Evolución mensual de las defunciones; la línea punteada es el promedio mensual.",
              dcc.Graph(id="g-lineas", config={"displaylogo": False}), "completo"),
        panel("Homicidios con códigos X950–X959: agresión con disparo de otras armas de fuego "
              "y las no especificadas. Municipio de ocurrencia de la defunción.",
              dcc.Graph(id="g-violentas", config={"displaylogo": False})),
        panel("Municipios con menor número de defunciones registradas en 2019 (con al menos "
              "una defunción). Al no disponer de población en los archivos, el índice se mide "
              "como total de muertes; en caso de empate se ordena alfabéticamente.",
              dcc.Graph(id="g-pie", config={"displaylogo": False})),
        panel("Barras apiladas por sexo; los departamentos se ordenan de mayor a menor total.",
              dcc.Graph(id="g-sexo", config={"displaylogo": False}), "completo"),
        panel("Histograma de defunciones agrupando GRUPO_EDAD1 en las categorías del ciclo de "
              "vida definidas en la tabla de referencia.",
              dcc.Graph(id="g-hist", config={"displaylogo": False}), "completo"),
    ]),

    html.Footer(className="pie", children=[
        "Fuente: DANE – Estadísticas Vitales (EEVV) 2019 · ",
        html.A("microdatos.dane.gov.co/index.php/catalog/696",
               href="https://microdatos.dane.gov.co/index.php/catalog/696", target="_blank"),
        " · Maestría en Inteligencia Artificial – Aplicaciones I · Universidad de La Salle",
    ]),
])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@app.callback(
    Output("f-dpto", "value"), Output("f-sexo", "value"), Output("f-mes", "value"),
    Input("g-mapa", "clickData"), Input("btn-reset", "n_clicks"),
    State("f-dpto", "value"), State("f-sexo", "value"), State("f-mes", "value"),
    prevent_initial_call=True,
)
def interaccion_mapa(click, _reset, dpto_actual, sexo, mes):
    if ctx.triggered_id == "btn-reset":
        return [], [1, 2, 3], [1, 12]
    cod = click["points"][0]["location"]
    actual = list(dpto_actual or [])
    actual = [c for c in actual if c != cod] if cod in actual else actual + [cod]
    return actual, sexo, mes


@app.callback(
    Output("g-mapa", "figure"), Output("g-lineas", "figure"), Output("g-violentas", "figure"),
    Output("g-pie", "figure"), Output("t-causas", "data"), Output("g-sexo", "figure"),
    Output("g-hist", "figure"),
    Output("kpi-total", "children"), Output("kpi-hombres", "children"),
    Output("kpi-mujeres", "children"), Output("kpi-x95", "children"),
    Input("f-dpto", "value"), Input("f-sexo", "value"), Input("f-mes", "value"),
)
def actualizar(dpto, sexo, mes):
    d = filtrar(dpto, sexo, mes)
    # El mapa muestra siempre todos los departamentos (con los filtros de sexo y mes)
    # y resalta los seleccionados.
    d_mapa = filtrar(None, sexo, mes)
    figs = [fig_lineas(d), fig_violentas(d), fig_menor_mortalidad(d), fig_sexo_dpto(d),
            fig_histograma(d)]
    if dpto:
        nombres = ", ".join(titulo(dptos[c]) for c in dpto[:3]) + ("…" if len(dpto) > 3 else "")
        for f in figs:
            f.update_layout(title_text=f"{f.layout.title.text} · {nombres}")
    lineas, violentas, pie, sexo_fig, hist = figs
    return (
        fig_mapa(d_mapa, dpto), lineas, violentas, pie,
        tabla_causas(d), sexo_fig, hist,
        fmt(len(d)), fmt((d["SEXO"] == 1).sum()), fmt((d["SEXO"] == 2).sum()),
        fmt(d["COD_MUERTE"].str.startswith("X95").sum()),
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
