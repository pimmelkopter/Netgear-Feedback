import platform
if platform.system() == "Windows":
    import services.mock_hardware  # Registriert die Module
from ..src import main

main.main()