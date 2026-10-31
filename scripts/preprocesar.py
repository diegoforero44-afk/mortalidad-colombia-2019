"""
Preprocesamiento de los archivos del DANE (Estadísticas Vitales 2019).

Lee los tres Excel originales de data/raw/ y genera archivos livianos en
data/processed/ que la aplicación Dash carga al iniciar. Esto evita leer un
Excel de ~19 MB en cada arranque del servidor (importante en el plan gratuito
de Render, que tiene memoria y tiempo de arranque limitados).

Uso:
    python scripts/preprocesar.py
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
OUT = BASE / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def procesar_defunciones() -> pd.DataFrame:
    cols = ["COD_DANE", "COD_DEPARTAMENTO", "COD_MUNICIPIO", "MES", "SEXO",
            "GRUPO_EDAD1", "MANERA_MUERTE", "COD_MUERTE"]
    df = pd.read_excel(RAW / "NoFetal2019.xlsx", sheet_name="No_Fetales_2019",
                       usecols=cols, dtype={"COD_DANE": str, "COD_DEPARTAMENTO": str,
                                            "COD_MUNICIPIO": str, "COD_MUERTE": str})
    df["COD_DANE"] = df["COD_DANE"].str.zfill(5)
    df["COD_DEPARTAMENTO"] = df["COD_DEPARTAMENTO"].str.zfill(2)
    df["COD_MUERTE"] = df["COD_MUERTE"].str.strip().str.upper()
    df.to_csv(OUT / "defunciones_2019.csv.gz", index=False, compression="gzip")
    print(f"defunciones: {len(df):,} registros")
    return df


def procesar_divipola() -> pd.DataFrame:
    # La hoja "Hoja3" contiene los valores (Hoja1 solo tiene fórmulas XLOOKUP)
    raw = pd.read_excel(RAW / "Divipola.xlsx", sheet_name="Hoja3", header=None,
                        skiprows=2, dtype=str)
    div = raw.iloc[:, :7]
    div.columns = ["COD_DEPARTAMENTO", "DEPARTAMENTO", "COD_DANE", "MUNICIPIO",
                   "TIPO", "LONGITUD", "LATITUD"]
    div = div.dropna(subset=["COD_DANE"])
    div["COD_DANE"] = div["COD_DANE"].str.strip().str.zfill(5)
    div["COD_DEPARTAMENTO"] = div["COD_DEPARTAMENTO"].str.strip().str.zfill(2)
    for c in ["LONGITUD", "LATITUD"]:
        div[c] = pd.to_numeric(div[c].str.replace(",", ".", regex=False), errors="coerce")
    div.to_csv(OUT / "divipola.csv", index=False)
    print(f"divipola: {len(div):,} municipios, {div['COD_DEPARTAMENTO'].nunique()} departamentos")
    return div


def procesar_codigos() -> pd.DataFrame:
    raw = pd.read_excel(RAW / "CodigosDeMuerte.xlsx", sheet_name="Final", header=None,
                        skiprows=9, dtype=str)
    cod = raw.iloc[:, :6]
    cod.columns = ["CAPITULO", "NOMBRE_CAPITULO", "COD_3", "DESC_3", "COD_4", "DESC_4"]
    cod = cod.dropna(subset=["COD_4"])
    for c in cod.columns:
        cod[c] = cod[c].astype(str).str.strip()
    cod["COD_4"] = cod["COD_4"].str.upper()
    cod.to_csv(OUT / "codigos_muerte.csv", index=False)
    print(f"códigos CIE-10: {len(cod):,}")
    return cod


if __name__ == "__main__":
    procesar_divipola()
    procesar_codigos()
    procesar_defunciones()
