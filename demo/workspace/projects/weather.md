# Pipeline date meteo — nota proiectului

Ingest zilnic din API-ul public al serviciului meteo, normalizare în Postgres, raport de calitate.

## Session 2026-09-21 (seara) - RESUME HOOK — prima rulare completă pe date reale

- Ingest: 15.956 înregistrări, 0 nerezolvate.
- Task zilnic programat la 06:00.

**NEXT.** (1) ✅ făcut: task zilnic. (2) Decizie: păstrăm stațiile fără coordonate sau le excludem. (3) Completare retroactivă pentru 2024.

## Session 2026-09-21 (dimineața) - spec-ul

**NEXT — blocat pe utilizator (§8 din spec):** (1) de când începe istoricul: 2010 sau 2018; (2) schema separată `weather` sau tabel comun. Apoi: plan de implementare.

## Session 2026-09-23 - RESUME HOOK — cheia API expiră în noiembrie

- Sursa anunță chei noi obligatorii din 1 noiembrie.
- **NEXT (decizia utilizatorului):** cont gratuit nou acum sau migrare pe sursa alternativă. `C:\work\weather\docs\sources.md`
