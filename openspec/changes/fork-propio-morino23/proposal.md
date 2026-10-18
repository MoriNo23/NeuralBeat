# Proposal

## Why

El autor original responde issues lentamente y el usuario ya mantiene cambios locales propios (paddings de UI, correcciones del README, guía `LEEME.md` en español). Para poder publicar sus cambios y divergir sin fricción necesita un fork real (`MoriNo23/NeuralBeat`) que conserve el vínculo con el upstream, cumpla la licencia Apache-2.0 (atribución y aviso de modificaciones) y deje de apuntar FUNDING y URLs de clonado al autor original.

## What Changes

- Crear fork real en GitHub: `MoriNo23/NeuralBeat` (público), conservando `upstream` = `Aegean-E/NeuralBeat` para traer correcciones del autor cuando quiera.
- Higiene de repositorio antes de publicar: `.gitignore` solo para artefactos de test; `.agents/` (2032 archivos, ≈27 MB de skills del mantenedor) **SÍ se publica** por decisión explícita del autor; commitear los cambios locales existentes (paddings, fixes del README y `.agents/`) con mensajes claros.
- Identidad y atribución: título de ventana y diálogo About identifican el fork manteniendo el crédito Apache-2.0 a Ægean; `.github/FUNDING.yml` deja de apuntar al Patreon del autor original; `NOTICE` con la declaración de modificaciones (Apache-2.0 §4b).
- Documentación: `LEEME.md` y `README.md` apuntan al repositorio canónico del fork y declaran el estado de fork.
- Rama: se publica `Base` tal cual (cero fricción para mergear del upstream más adelante); sin renombrar.
- **Sin cambios de comportamiento de la aplicación** (solo identidad, metadatos y enlaces). Sin breaking changes para usuarios.

## Capabilities

### New Capabilities

Ninguna. Cambio de tooling/repositorio/documentación: `skip_specs: true` en `.openspec.yaml`. El único efecto en strings de la app (título/About) es identidad, no comportamiento especificable.

### Modified Capabilities

Ninguna (el proyecto no tiene specs todavía).

## Impact

- Git: nuevos remotos (`origin` = fork, `upstream` = original), primer push de `Base`.
- GitHub: repositorio nuevo bajo la cuenta `MoriNo23`.
- Archivos: `.gitignore`, subárbol `.agents/` (2032 archivos, ≈27 MB, se publica), `SourceCode.py` (strings de título/About), `README.md`, `LEEME.md`, `.github/FUNDING.yml`, nuevo `NOTICE`.
- Sin cambios en dependencias ni en el motor de audio.
