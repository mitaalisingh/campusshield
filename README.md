# CampusShield

**Bridging the gap between the air-conditioned admin office and the hostel room on the top floor.**

Environmental Hacks (Bharat Builds Tour) · Track: Heat and Water · Solo build

## The problem

In May 2024 at VIT Bhopal, exams ran in 44°C heat while the campus had no water, and it ended in a student protest. In summer 2026 non-AC hostel rooms were physically unbearable at night. Decisions about exam timings, water logistics and cooling spaces are made by people sitting in AC offices who look at a weather app showing "39°C" and think it is manageable. They never see what the unshaded walk between hostel and exam hall feels like, or that the hostel water tanks run empty at the exact hour heatstroke risk peaks.

## What it does

Search any campus in India and CampusShield gives the administration:

- **Reality gap**: AC office vs outside air vs top-floor hostel room vs unshaded walking path, side by side.
- **Heat-stress level** from WBGT (heat + humidity + sun), the number that actually decides heatstroke risk, with loo (hot dry wind) detection.
- **7-day outlook**: pick a day to plan exams and events.
- **Water depletion clock**: when the tanks run dry given heat-driven usage, and how many tankers to order.
- **Action cards**: concrete decisions ("shift exams to 6–9 AM", "open the library as a cool sleeping zone tonight", "order N tankers before 8 AM").
- **One-click notice** for wardens and students.
- **Replay mode** for 26 May 2024 (44.6°C near campus) using real historical data.

## Where AWS fits

The whole app (dashboard and API) runs on **AWS Lambda behind a Lambda Function URL** in `ap-south-1` (Mumbai). A single Python function serves the page and the `/api/*` endpoints and has no third-party dependencies.

## How it is built

- `core.py`: weather fetch, WBGT, room/path models, water simulation, action engine.
- `api.py`: request routing shared by Lambda and the local server.
- `lambda_function.py`: Lambda entry point.
- `server.py`: local dev server (`python3 server.py`, then open http://localhost:8000).
- `web/index.html`: dashboard (vanilla JS, no build step).
- `build_zip.sh`: builds the Lambda deployment package.

Data sources: [Open-Meteo](https://open-meteo.com) (forecast and historical weather, CC BY 4.0) and [OpenStreetMap Nominatim](https://nominatim.org) (campus search, © OpenStreetMap contributors).

## Honest limits

- WBGT is an approximation for an unshaded person in sun, and it runs on the high side. It is not calibrated against on-campus sensors.
- Hostel-room and walking-path temperatures are modelled from real weather (roofs store heat, concrete radiates it), not measured.
- **Water tank levels are simulated** from student count and tank capacity. There are no live sensors yet.

## Future scope

1. Real tank-level and room-temperature sensors through AWS IoT Core, replacing the simulations.
2. Amazon Bedrock to write the Director's daily briefing, and Hindi notices.
3. Automatic SNS / WhatsApp alerts to wardens when a threshold is crossed.
4. DynamoDB history so a campus can show the pattern to its governing body.
5. Calibrate WBGT against sensors (full Liljegren method).
6. Per-institution heat-action policy with mandatory exam-shift thresholds.

## AI tools used

Built with Claude Code (Anthropic) as a coding assistant.
