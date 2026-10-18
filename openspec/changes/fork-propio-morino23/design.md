# Design

## Context

Ver `proposal.md` para motivación. Estado actual:

- Clon local con `origin` = `Aegean-E/NeuralBeat`, rama `Base` (default del upstream) con cambios locales sin commitear en `README.md` y `SourceCode.py` (paddings, fixes de tipeo).
- Sin trackear dentro de la app: `LEEME.md` (guía en español), `openspec/` (tooling de planificación), `.agents/` (27 MB de skills del harness).
- `gh` autenticado como `MoriNo23` con scope `repo`; no existe fork todavía.
- Licencia Apache-2.0 (LICENSE presente); `.github/FUNDING.yml` y enlaces del README apuntan al autor original.

## Goals / Non-Goals

**Goals:**
- Fork real público `MoriNo23/NeuralBeat` con `upstream` preservado para traer correcciones.
- Cumplimiento Apache-2.0 (atribución + aviso de modificaciones) sin borrar el crédito original.
- Repositorio publicado íntegro (código + `.agents/` + `openspec/`) y sin secretos.
- Docs apuntando al repositorio canónico del fork.

**Non-Goals:**
- Renombrar el proyecto o la rama; reescribir historia (nada de squash/rebase de lo ya decido).
- Cambiar la licencia o el motor; versionado nuevo (se mantiene 1.0.0 hasta que aterrice el modo visual).
- CI automatizado (diferido).

## Decisions

1. **Fork real (opción A) sobre repo independiente o solo local.** Mantiene el vínculo (`forked from`), permite `git fetch upstream` gratis y conserva la trazabilidad. Repo independiente perdería eso; solo local no publica nada. Se crea público: el upstream es Apache-2.0 público y el objetivo es mantener el fork como proyecto propio.
2. **Rama `Base` conservada** (no renombrar a `main`): cero fricción para mergear del upstream en el futuro; renombrar rompería la comparabilidad y obligaría a mapeos manuales.
3. **Topología de remotos:**
   ```
   origin   -> github.com/MoriNo23/NeuralBeat   (push/fetch)
   upstream -> github.com/Aegean-E/NeuralBeat   (solo fetch)
   ```
   `origin` original se renombra a `upstream` **antes** de agregar el nuevo `origin`, y los pushes siempre se hacen explícitos (`git push origin Base`) para eliminar el riesgo de publicar en el repo del autor.
4. **Atribución: LICENSE intacto + `NOTICE` + About con doble crédito.** Apache-2.0 §4(b) exige aviso de modificaciones; borrar las menciones al autor sería incumplimiento. La alternativa "limpiar el repo de todo lo del autor" se rechaza.
5. **`FUNDING.yml` sin el Patreon del autor original**: en el fork, redirigir financiamiento ajeno sería engañoso; se deja vacío/eliminado hasta que exista financiamiento propio.
6. **Publicación íntegra, incluido `.agents/`:** decisión explícita del mantenedor (allí viven sus skills: 2032 archivos, ≈27 MB, sin archivos mayores de 2 MB). `.gitignore` solo suma artefactos de test; `openspec/` también se publica. Commits separados para paddings, fixes del README y `.agents/` antes del push. Alternativa descartada por el usuario: ignorar `.agents/`.
7. **`skip_specs: true`**: cambio de tooling/repositorio/documentación, sin comportamiento especificable más allá de strings de identidad.

## Risks / Trade-offs

- [Push accidental al upstream] → renombrar remotos primero; push explícito a `origin`; `upstream` sin credenciales de escritura en la práctica.
- [Divergencia futura difícil de mergear] → no se reescribe historia local publicada; los cambios futuros van en commits nuevos.
- [Incumplir la licencia por atribución incompleta] → tarea de verificación explícita: LICENSE intacto, NOTICE presente, About con crédito, y `openspec validate`/revisión final de archivos.
- [Secretos dentro de `.agents/` u `openspec/`] → revisión pre-push con búsqueda de credenciales en todo el árbol (énfasis `.agents/`); el escaneo inicial solo encontró menciones genéricas de tokens en documentación de skills, sin valores reales; la config de usuario vive en `~/.neuralbeat/`, fuera del repo.
- [Skills de terceros con licencias propias y peso extra del repo] → decisión explícita del mantenedor; el `NOTICE` aclara que `.agents/` contiene skills de terceros que conservan sus licencias.
- [Expectativa de que el fork "responde issues" del upstream] → el README declara que es un fork mantenido por MoriNo23, no el proyecto original.

## Migration Plan

1. Commitear cambios locales + higiene de `.gitignore`.
2. `gh repo fork Aegean-E/NeuralBeat --remote=false`.
3. `git remote rename origin upstream` + `git remote add origin https://github.com/MoriNo23/NeuralBeat.git`.
4. `git push -u origin Base`.
   Rollback: `git remote rename upstream origin` y, si hiciera falta, borrar el fork en GitHub (no se toca el remoto del autor).
