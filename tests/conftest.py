"""Conftest de tests: entorno de importacion determinista.

Los modulos de test mockean dependencias pesadas con el patron
``if mod_name not in sys.modules: sys.modules[mod_name] = mock``. Sin este
conftest, el resultado dependia del orden de coleccion de pytest:

- un test que mockea ``tkinter`` pero no ``matplotlib`` rompia la coleccion
  cuando matplotlib real importaba ``tkinter.filedialog`` sobre el mock;
- ``test_dsp_generators`` reemplazaba ``sys.modules['tkinter']`` sin guarda,
  desincronizando ``SourceCode.tk`` del modulo visible por tests posteriores.

Aqui se pre-instalan una sola vez los mocks de UI/audio/salida (numpy y scipy
quedan REALES, que es lo que usan los tests DSP) y se configuran las
constantes de Tk que algunos tests comparan literalmente. Cualquier orden de
import queda entonces equivalente.
"""

import sys
from unittest.mock import MagicMock

MOCK_MODULES = {
    'tkinter': MagicMock(),
    'tkinter.ttk': MagicMock(),
    'tkinter.messagebox': MagicMock(),
    'tkinter.simpledialog': MagicMock(),
    'tkinter.filedialog': MagicMock(),
    'ttkbootstrap': MagicMock(),
    'sounddevice': MagicMock(),
    'matplotlib': MagicMock(),
    'matplotlib.figure': MagicMock(),
    'matplotlib.backends': MagicMock(),
    'matplotlib.backends.backend_tkagg': MagicMock(),
}
for mod_name, mock_obj in MOCK_MODULES.items():
    if mod_name not in sys.modules:
        sys.modules[mod_name] = mock_obj

# Constantes de Tk que los tests comparan literalmente: con tkinter mockeado,
# tk.END debe ser 'end' (igual que en tkinter real), no un MagicMock.
if isinstance(sys.modules.get('tkinter'), MagicMock):
    sys.modules['tkinter'].END = 'end'
    sys.modules['tkinter'].TclError = Exception
