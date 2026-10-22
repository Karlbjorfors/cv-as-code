# CV som kod

Ett CV som byggs från **data + mall + kod** i stället för att redigeras för hand i ett
ordbehandlingsprogram. Innehållet ligger i YAML, utseendet i en Jinja/HTML-mall med print-CSS,
och ett Python-script gör en PDF av det med headless Chromium. Sedan kontrollerar scriptet att
resultatet håller måttet: exakt en sida och klickbara länkar.

![Exempel-CV renderat från examples/](examples/example-cv.png)

Exemplet ovan är en påhittad person ([`examples/`](examples/)). Mitt riktiga CV renderas med
samma kod, men innehåll, kontaktuppgifter och foto ligger privat och finns inte i det här repot.

## Varför?

- **Ett CV per ansökan utan copy-paste.** Varje annons får en egen `cv.yml` med anpassad profil
  och utvalda erfarenheter. Mallen och kontaktuppgifterna delas.
- **AI skriver text, kod gör resten.** En AI-agent kan skriva en anpassad `cv.yml`, men den ska inte
  "rita" PDF:er. Layout, rendering och kontroller är deterministisk kod som alltid ger samma resultat.
- **Kontroller i stället för att hoppas.** Ett CV som råkat bli två sidor, eller där
  LinkedIn-länken bara är text, stoppas innan det skickas.
- **Versionshanterat.** Varje ändring syns i Git, och gamla CV:n kan återskapas exakt.

## Snabbstart

Kräver [uv](https://docs.astral.sh/uv/) och Chromium eller Google Chrome.

```bash
uv run render.py --cv examples/cv.yml --contact examples/contact.yml --out out/cv.pdf
# ok: out/cv.pdf (1 page(s), 4 links verified)
```

`render.py` är ett fristående script med inbyggd beroendedeklaration
([PEP 723](https://peps.python.org/pep-0723/)). `uv` installerar `jinja2` och `pyyaml` automatiskt
i en isolerad miljö, så du behöver ingen virtualenv eller `requirements.txt`.

| Flagga | Betydelse |
|---|---|
| `--cv FIL` | CV-innehållet (`cv.yml`) |
| `--contact FIL` | Kontaktuppgifter (`contact.yml`) |
| `--out FIL` | Var PDF:en hamnar |
| `--photo FIL` | Porträtt (jpg/png/svg). Går före `photo:` i `contact.yml` |
| `--template FIL` | Annan mall än `templates/cv.html.j2` |
| `--html` | Spara även den renderade HTML:en bredvid PDF:en (bra för felsökning) |
| `--allow-multipage` | Stäng av kravet på en sida |

Webbläsaren hittas automatiskt (`chromium`, `chromium-browser`, `google-chrome-stable`,
`google-chrome`), eller anges med `CHROME=/sökväg/till/webbläsare`.

## Dataformat

Datan är uppdelad i två filer med flit. Kontaktuppgifter ändras sällan och är personliga, medan
CV-innehållet skrivs om för varje ansökan.

### `contact.yml`

```yaml
name: Alex Exempel
email: alex@example.com        # blir en mailto:-länk
phone: 070-000 00 00           # valfri
location: Malmö                # valfri
photo: avatar.svg              # valfri, sökväg relativt contact.yml
links:                         # visas i den här ordningen i sidhuvudet
  - label: LinkedIn
    url: https://www.linkedin.com/in/example
  - label: Github
    url: https://github.com/example
```

Varje `url`, plus `mailto:` för e-posten, **måste** finnas som klickbar länk i den färdiga PDF:en,
annars avbryts renderingen.

### `cv.yml`

```yaml
lang: sv                       # sv | en, styr rubrikerna
kicker: Systemutveckling · Automatisering   # liten rad ovanför namnet
profile: >-
  Löptext för profilen ...
skills:                        # högerspalten
  - label: Utveckling
    items: Python, TypeScript, SQL
experience:                    # poster: years, title, org?, bullets?, desc?, url?
  - years: 2024–
    title: Systemutvecklare
    org: Exempelbolaget AB, Malmö
    bullets:
      - Byggde en intern webbportal ...
projects:                      # samma postformat som experience
  - years: 2025
    title: Bokningsapp
    url: https://example.com   # gör titeln klickbar
    desc: Kort beskrivning ...
education:                     # years, title, org
  - years: 2023–24
    title: Systemutvecklare .NET/Python
    org: Yrkeshögskola, Malmö
volunteer:                     # samma postformat som experience
  - years: 2022–
    title: Kassör
    desc: ...
```

Alla sektioner utom `profile` och `skills` är valfria och hoppas över om de saknas. Tips: sätt
citattecken runt punkter som innehåller `: ` (kolon + mellanslag), annars tolkar YAML dem som
nyckel/värde. Skriv årtal som `"2025"` om du vill vara säker på att de blir text.

## Så fungerar mallen

[`templates/cv.html.j2`](templates/cv.html.j2) är en vanlig HTML-sida med inbäddad CSS, skriven för
utskrift i stället för skärm:

- **`@page { size: A4; margin: 8mm 16mm; }`** styr pappersformat och marginaler. Chromiums
  `--print-to-pdf` respekterar detta, och med `--no-pdf-header-footer` försvinner webbläsarens
  datum och URL.
- **Typografi i `pt`**, inte `px`, så storlekarna motsvarar ett tryckt dokument (brödtext 8,4 pt).
- **CSS grid** för layouten: sidhuvud (foto + namn), en tvåspaltig topp (profil 1,9 fr,
  kompetenser 1 fr) och poster med en smal årtalskolumn och innehåll bredvid.
- **En Jinja-makro, `entry()`**, ritar alla poster i erfarenhet, projekt och ideellt engagemang.
  Därför har de samma format och samma valfria fält.
- **Autoescape är på**, så tecken som `&` och `<` i YAML-texten blir korrekt HTML.
- **Fotot bäddas in som base64** (`data:`-URI). HTML:en är då helt fristående, och PDF:en kan
  renderas utan nätverk eller lösa filer.
- **Rubrikerna översätts** via en liten tabell överst i mallen (`sv`/`en`).

### Lägga till en sektion

1. Lägg till en nyckel i `cv.yml`, t.ex. `certifications:` med samma postformat.
2. I mallen: lägg till nyckeln i loopen `{% for key in ["experience", "projects"] %}` om den ska se
   ut som erfarenhet, eller skriv ett eget block.
3. Lägg till rubriken i översättningstabellen `t` för både `sv` och `en`.
4. Rendera med `--html` och öppna HTML-filen i webbläsaren för att justera CSS snabbt. Kör sedan
   utan flaggan för att få PDF och kontroller.

## Kontroller

Efter utskrift läser `render.py` PDF:en och kontrollerar:

| Kontroll | Hur | Varför |
|---|---|---|
| Exakt en sida | Räknar `/Type /Page`-objekt i PDF:en | Rekryterare läser sida ett; en sida två som råkat uppstå ser slarvig ut |
| Klickbara länkar | Letar efter varje `url` och `mailto:` som `/URI`-annotation | Länkar som bara är text går inte att klicka på i en PDF |

Kontrollerna läser PDF-bytes direkt och behöver inga extra verktyg. Om något fallerar listas varje
problem och scriptet avslutas med felkod 1, så det fungerar även i ett automatiserat flöde.

## Hur mallen används i vårt arbetsflöde

Repot är renderingssteget i **Jobbsökassistenten**, ett privat fritidsprojekt. Det är ett system av
AI-agenter som hjälper mig söka jobb, med en människa som fattar alla beslut. Flödet för en
ansökan:

```
 Annons                Profil (privat)            Skribent-agent             cv-as-code             Människa
 ─────────            ─────────────────          ──────────────             ───────────            ─────────
 JobTech-API   ──►    verifierade fakta,   ──►   skriver anpassad    ──►    render.py:      ──►    granskar,
 (Platsbanken)        erfarenheter,              cv.yml för just            mall + data            justerar,
 → annons.md          contact.yml, foto          den här annonsen           → PDF + kontroller     skickar själv
```

1. **Annonsen hämtas** från Arbetsförmedlingens öppna JobTech-API, med strukturerade fält som krav,
   sista ansökningsdag och ansökningslänk. Den sparas som markdown.
2. **Profilen** är en privat kunskapsbas med mina erfarenheter, skrivna och verifierade av mig. Där
   finns också `contact.yml` och foto. Ingen av den datan finns i det här repot.
3. **En skribent-agent** (Claude Code) matchar annonsens krav mot profilen och skriver en anpassad
   `cv.yml`. Regeln är att den **bara får använda fakta från profilen**: inga påhittade siffror,
   verktyg eller titlar. AI:n används för det som kräver omdöme och fri text, inget annat.
4. **`render.py` gör PDF:en och kontrollerar den.** Om CV:t blev två sidor eller en länk saknas
   misslyckas steget, och agenten får korta texten eller rätta datan och försöka igen. Det blir en
   enkel återkopplingsloop utan att någon människa behöver märka felet.
5. **En människa granskar och skickar.** Inget skickas automatiskt. Systemet tar fram underlag, men
   beslutet och ansökan är mina.

Uppdelningen gör att samma mall och samma kontroller gäller för varje ansökan, oavsett vilken
agent eller modell som skrev texten. Det gör det också lätt att jämföra olika AI-modeller på samma
annons, eftersom bara `cv.yml` skiljer sig.

### Personuppgifter och hemligheter

- Repot innehåller **bara kod, mall och påhittad exempeldata**.
- Riktiga `contact.yml`, foto och CV-innehåll ligger i en privat katalog utanför repot och skickas
  in med `--cv` och `--contact`.
- `.gitignore` stoppar vanliga misstag: `out/`, `private/`, `*.local.yml` och bilder utanför
  `examples/`.

## Felsökning

| Problem | Lösning |
|---|---|
| `no Chromium/Chrome found` | Installera Chromium, eller sätt `CHROME=/sökväg/till/chrome` |
| `expected 1 page, got 2` | Korta texten, ta bort en punkt eller en äldre post. Rendera med `--html` för att se var det tar slut |
| `link missing or not clickable` | Kontrollera att mallen ritar länken som `<a href=...>` och att URL:en i YAML är exakt samma |
| `cannot read ... could not find expected ':'` | YAML-syntaxfel. Sätt citattecken runt texten på raden som anges |
| Fel typsnitt i PDF:en | Mallen använder Arial/Helvetica och faller tillbaka på systemets sans-serif. Installera t.ex. `ttf-liberation` för samma metrik som Arial |

## Licens

MIT, se [LICENSE](LICENSE).
