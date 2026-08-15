"""Extract Sri Chinmoy Marathon Swim results from result PDFs via the Claude API.

One API call per PDF; the PDF is sent as a document block and Claude returns a
structured JSON payload (one record per swimmer) that we dump to results/<year>.json.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Optional

import anthropic
import typer
from pydantic import BaseModel

app = typer.Typer(add_completion=False)

BASE = Path(__file__).parent
PDF_DIR = BASE / "pdf"
OUT_DIR = BASE / "results"

MODEL = "claude-sonnet-5"


class Result(BaseModel):
    rank: Optional[int]
    status: str  # FINISHED | DNF | DNS | HC (hors concours) | OTHER
    last_name: str
    first_name: str
    year_of_birth: Optional[int]
    age: Optional[int]
    nationality: Optional[str]
    home_city: Optional[str]
    club: Optional[str]
    start_number: Optional[str]
    split_meilen: Optional[str]
    finish_time: Optional[str]
    category_raw: str
    gender: str  # M | F | MIXED | UNKNOWN
    age_class: str  # MAIN | MASTERS | JUNIORS | OPEN | UNKNOWN
    wetsuit: bool
    relay: bool
    relay_team_name: Optional[str]
    remark: Optional[str]


class RaceResults(BaseModel):
    year: int
    event_date: Optional[str]
    event_name: Optional[str]
    distance_km: Optional[float]
    weather: Optional[str]
    water_temp: Optional[str]
    results: list[Result]


PROMPT = """Du erhältst die offizielle Rangliste des Sri Chinmoy Marathon-Schwimmens \
(Zürichsee, Rapperswil–Zürich) für ein Jahr.

Extrahiere JEDEN Teilnehmer als eigenen Datensatz. Regeln:

- Kategorie-Überschriften (z.B. "Männer Hauptklasse (16 bis 49 Jahre)", "Frauen Masters", \
"Herren - Neoprenanzug", "Staffeln / Relays") bestimmen `category_raw`, `gender`, \
`age_class`, `wetsuit` und `relay` für alle darunter stehenden Zeilen.
  - gender: M (Männer/Herren/Men), F (Frauen/Damen/Women), MIXED (gemischte Staffel), sonst UNKNOWN
  - age_class: MAIN (Hauptklasse/Main Class), MASTERS, JUNIORS, OPEN (offen für alle Alter), sonst UNKNOWN
  - wetsuit: true bei Neoprenanzug / wetsuit / "with swim aid"
  - relay: true bei Staffel / Relay
- Zeilen "Meeting-Rekord", "Meeting Rekord", "Letzte Bestzeit", "Last Events Best Performance" \
sind KEINE Teilnehmer — ignoriere sie.
- Tabellenköpfe ("Rang Name Vorname ...") ignorieren.
- `status`: FINISHED wenn eine Endzeit vorhanden ist; DNF bei DNF/aufgegeben; DNS bei DNS/Forfait/nicht \
gestartet; HC wenn ausser Konkurrenz (z.B. "H.C." oder Start in Meilen); sonst OTHER.
- `rank` nur wenn eine Rangnummer angegeben ist, sonst null.
- Zeiten als Text genau wie gedruckt übernehmen, z.B. "8h 03m 35s". `split_meilen` ist die \
Zwischenzeit bei Meilen (falls vorhanden). Achtung: In manchen Jahrgängen steht die Endzeit VOR der \
Zwischenzeit bei Meilen ("Endzeit / bei Meilen"), in anderen danach ("bei Meilen / Zeit") — \
ordne sie anhand der Spaltenüberschrift korrekt zu. Die Endzeit ist immer die grössere Zeit.
- `year_of_birth` (Jahrgang) bzw. `age` (Alter) je nachdem was gedruckt ist; das jeweils andere null.
- Bei Staffeln: `relay_team_name` = Teamname; pro Schwimmer einen Datensatz, oder einen Datensatz \
pro Team falls keine Einzelnamen genannt sind.
- Nichts erfinden: fehlende Werte = null.

Gib das Ergebnis als JSON gemäss Schema zurück."""


def schema_of(model: type[BaseModel]) -> dict:
    """JSON schema with additionalProperties:false everywhere (API requirement)."""
    s = model.model_json_schema()

    def fix(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                node.setdefault("required", list(node.get("properties", {})))
            # Optional[X] renders as anyOf[X, null] — fine. Strip unsupported keys.
            for k in ("minLength", "maxLength", "minimum", "maximum", "format", "default"):
                node.pop(k, None)
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(s)
    return s


def extract_pdf(client: anthropic.Anthropic, pdf: Path, year: int) -> dict:
    data = base64.standard_b64encode(pdf.read_bytes()).decode()
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": schema_of(RaceResults)},
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": data,
                        },
                    },
                    {"type": "text", "text": f"{PROMPT}\n\nJahrgang: {year}"},
                ],
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(f"refused: {message.stop_details}")
    text = next(b.text for b in message.content if b.type == "text")
    payload = json.loads(text)
    payload["_usage"] = {
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "stop_reason": message.stop_reason,
    }
    return payload


@app.command()
def main(
    years: Optional[str] = typer.Option(None, help="Comma-separated years, default: all with a text layer"),
    force: bool = typer.Option(False, help="Re-extract even if the JSON already exists"),
) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    pdfs = [p for p in pdfs if int(p.name[:4]) >= 2002 and "Startliste" not in p.name]
    if years:
        wanted = {y.strip() for y in years.split(",")}
        pdfs = [p for p in pdfs if p.name[:4] in wanted]

    for pdf in pdfs:
        year = int(pdf.name[:4])
        out = OUT_DIR / f"{year}.json"
        if out.exists() and not force:
            typer.echo(f"{year}: skip (exists)")
            continue
        try:
            payload = extract_pdf(client, pdf, year)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"{year}: ERROR {exc}")
            continue
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        u = payload["_usage"]
        typer.echo(
            f"{year}: {len(payload['results'])} rows "
            f"(in {u['input_tokens']}, out {u['output_tokens']}, {u['stop_reason']})"
        )


if __name__ == "__main__":
    app()
