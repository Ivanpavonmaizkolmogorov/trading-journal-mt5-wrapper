# ===================================================================
#  SCRIPT DE INSTALACIÓN PARA EL SERVIDOR DE TRADING (Windows VPS)
# ===================================================================

# --- CONFIGURACIÓN (Modifica esto según sea necesario) ---
$ProjectDir = "C:\Users\XtrategyQ\Proyectos\trading-journal-mt5-wrapper"
$RepoURL = "https://github.com/Ivanpavonmaizkolmogorov/telegram-trading-journal/mt5-wrapper.git" # <-- ¡MUY IMPORTANTE CAMBIAR ESTO!
$ServiceName = "MT5API"
$NssmPath = "C:\nssm\nssm.exe" # <-- Ruta donde has dejado nssm.exe
# ---------------------------------------------------------

Write-Host "--- Iniciando configuración de la VPS ---" -ForegroundColor Green

# 1. Crear directorio y clonar el proyecto si no existe
if (-not (Test-Path $ProjectDir)) {
    Write-Host "Creando directorio del proyecto en $ProjectDir..."
    New-Item -Path $ProjectDir -ItemType Directory
}
Set-Location $ProjectDir

if (-not (Test-Path (Join-Path $ProjectDir ".git"))) {
    Write-Host "Clonando el repositorio desde $RepoURL..."
    git clone $RepoURL .
} else {
    Write-Host "El repositorio ya existe. Actualizando con git pull..."
    git pull
}

# 2. Crear entorno virtual e instalar dependencias
$PythonVenvPath = Join-Path $ProjectDir "venv\Scripts\python.exe"
Write-Host "Creando/verificando entorno virtual..."
python -m venv venv

Write-Host "Instalando dependencias desde requirements.txt..."
# Usamos el ejecutable de python del venv para instalar los paquetes
& $PythonVenvPath -m pip install -r requirements.txt

# 3. Instalar y configurar el servicio con NSSM
Write-Host "Configurando el servicio de Windows '$ServiceName'..."

# Si el servicio ya existe, lo detenemos y eliminamos para una instalación limpia
$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Service) {
    Write-Host "El servicio ya existe. Deteniendo y eliminándolo para reconfigurar..."
    & $NssmPath stop $ServiceName
    & $NssmPath remove $ServiceName confirm
}

# Argumentos para uvicorn
$Arguments = "-m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2"

# Instalar el servicio
& $NssmPath install $ServiceName $PythonVenvPath $Arguments
& $NssmPath set $ServiceName AppDirectory $ProjectDir
& $NssmPath set $ServiceName Description "API para el Trading Journal."
& $NssmPath set $ServiceName Start SERVICE_AUTO_START # Para que inicie con Windows

# 4. Iniciar el servicio
Write-Host "Iniciando el servicio '$ServiceName'..."
& $NssmPath start $ServiceName

Write-Host "--- ¡Configuración completada exitosamente! ---" -ForegroundColor Green

# Instalar los pre-requisitos:

    # Instala Git para Windows.

    # Instala Python para Windows.

    # Descarga nssm.exe y colócalo en C:\nssm\.

# Ejecutar tu script:

    # Abre una terminal de PowerShell como Administrador.

    # Clona tu proyecto una vez manualmente para obtener el script: git clone https://github.com/tu-usuario/tu-proyecto.git

    # Entra en la carpeta y ejecuta tu script: cd tu-proyecto y luego .\setup_vps.ps1.

    # El script se encargará de todo lo demás automáticamente. Has convertido un proceso manual de 15 minutos en un solo comando.