# Tasks

## 1. Higiene y commits previos

- [ ] 1.1 Sumar solo artefactos de test (`.pytest_cache/`, etc.) a `.gitignore`; `.agents/` NO se ignora. Verificar: `git check-ignore -v .agents` sin coincidencia y `.agents/` presente en `git status`.
- [ ] 1.2 Commit de los paddings de UI en `SourceCode.py`. Verificar con `git show --stat HEAD` que el commit contiene solo ese archivo.
- [ ] 1.3 Commit de fixes de `README.md`, `LEEME.md`, `openspec/` y del subárbol `.agents/` (2032 archivos: se publican). Verificar que `git status --porcelain` queda limpio (salvo lo ignorado) y que `git show --stat HEAD` incluye `.agents/`.
- [ ] 1.4 Revisión pre-push: búsqueda de credenciales en todo el árbol con énfasis en `.agents/` (`rg -i 'token|secret|apikey|password'`), confirmando que solo hay menciones genéricas en documentación y ningún valor real; `git ls-files .agents | wc -l` mayor que cero.

## 2. Identidad y atribución

- [ ] 2.1 Actualizar título de ventana y diálogo About: identifica el fork y su mantenedor, conserva el crédito original y la licencia. Verificar abriendo la app y revisando los strings con `rg`.
- [ ] 2.2 Crear `NOTICE` con la declaración de modificaciones (Apache-2.0 §4b) y la nota de que `.agents/` contiene skills de terceros que conservan sus propias licencias. Verificar: archivo presente con ambas menciones y `LICENSE` intacto (`git diff -- LICENSE` vacío).
- [ ] 2.3 Dejar `.github/FUNDING.yml` sin el Patreon/GitHub del autor original. Verificar el contenido final del archivo.
- [ ] 2.4 Actualizar `LEEME.md` y `README.md`: URL de clonado al fork y nota "fork mantenido por MoriNo23, no el proyecto original". Verificar con `rg` que las secciones de clonado solo apuntan al fork.
- [ ] 2.5 Commit de identidad. Verificar con `git show --stat HEAD` los archivos incluidos.

## 3. Fork y remotos

- [ ] 3.1 Crear el fork: `gh repo fork Aegean-E/NeuralBeat --remote=false`. Verificar con `gh repo view MoriNo23/NeuralBeat --json isFork` que devuelve `true`.
- [ ] 3.2 `git remote rename origin upstream` y `git remote add origin https://github.com/MoriNo23/NeuralBeat.git`. Verificar que `git remote -v` muestra `origin` = fork y `upstream` = original.
- [ ] 3.3 `git push -u origin Base`. Verificar que la rama existe en el fork y que su último commit coincide con el local (`gh api repos/MoriNo23/NeuralBeat/branches/Base --jq .commit.sha` vs `git rev-parse HEAD`).

## 4. Verificación final del fork

- [ ] 4.1 Verificar el estado público: `gh repo view MoriNo23/NeuralBeat` muestra el badge de fork y el README renderizado; `git fetch upstream` funciona sin tocar el repo del autor.
- [ ] 4.2 Verificar el árbol publicado: `gh api repos/MoriNo23/NeuralBeat/contents --jq '.[].name'` incluye `.agents` y `openspec`, y no lista archivos ignorados ni temporales.

## Workflow follow-up

- Archivar el change cuando la revisión esté satisfecha (`openspec archive fork-propio-morino23`).
- Confirmar que el remoto `upstream` queda solo para lectura en la práctica (nunca `git push upstream`).
