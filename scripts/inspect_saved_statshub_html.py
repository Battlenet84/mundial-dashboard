from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path


STAT_HINTS = {
    "player",
    "jugador",
    "team",
    "equipo",
    "shots",
    "shots on target",
    "sot",
    "fouls",
    "tackles",
    "cards",
    "xg",
    "xa",
    "passes",
    "hit rate",
    "average",
    "line",
    "odds",
}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._table_depth = 0
        self._in_cell = False
        self._cell = []
        self._row = []
        self._current_table = []
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
        if self._table_depth and tag == "tr":
            self._row = []
        if self._table_depth and tag in {"th", "td"}:
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._table_depth and tag in {"th", "td"}:
            self._in_cell = False
            self._row.append(" ".join("".join(self._cell).split()))
        if self._table_depth and tag == "tr" and self._row:
            self._current_table.append(self._row)
        if tag == "table" and self._table_depth:
            if self._table_depth == 1:
                self.tables.append(self._current_table)
            self._table_depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_cell:
            self._cell.append(data)


def likely_columns(headers: list[str]) -> list[str]:
    found = []
    for header in headers:
        normalized = re.sub(r"\s+", " ", header.strip().lower())
        if normalized in STAT_HINTS or any(hint in normalized for hint in STAT_HINTS):
            found.append(header)
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True)
    parser.add_argument("--source-page")
    args = parser.parse_args()

    path = Path(args.html)
    html = path.read_text(encoding="utf-8", errors="ignore")
    parsed = TableParser()
    parsed.feed(html)

    print("INSPECCION HTML STATSHUB")
    print("Este comando no consume API.")
    print(f"Archivo: {path}")
    if args.source_page:
        print(f"Pagina fuente: {args.source_page}")
    print(f"Titulo: {parsed.title.strip() or '-'}")
    print(f"Tablas detectadas: {len(parsed.tables)}")

    useful = False
    for index, table in enumerate(parsed.tables, start=1):
        headers = table[0] if table else []
        row_count = max(len(table) - 1, 0)
        candidates = likely_columns(headers)
        useful = useful or bool(candidates and row_count)
        print(f"Tabla {index}:")
        print(f"- Headers: {headers}")
        print(f"- Filas: {row_count}")
        print(f"- Posibles columnas stats: {candidates}")

    if not useful:
        print("No se encontraron datos tabulares en el HTML guardado. Probablemente la pagina carga datos dinamicamente.")


if __name__ == "__main__":
    main()

