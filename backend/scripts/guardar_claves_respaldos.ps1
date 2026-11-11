param([string]$Destino = "")
$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $backend "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "No se encontro Python en backend\venv." }

Write-Host "Pangea - Copia cifrada de las claves de recuperacion" -ForegroundColor Cyan
Write-Host "Elige un USB o una carpeta privada fuera de esta computadora."
Write-Host "Despues escribe dos veces una frase secreta de al menos 16 caracteres."
Write-Host "La frase no se muestra ni se envia al chat. Conserva la frase separada del archivo."

if (-not $Destino) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialogo = New-Object System.Windows.Forms.SaveFileDialog
    $dialogo.Title = "Guardar claves cifradas en USB o almacenamiento privado externo"
    $dialogo.Filter = "Paquete cifrado de Pangea (*.enc)|*.enc"
    $dialogo.FileName = "pangea-claves-$(Get-Date -Format 'yyyyMMdd-HHmmss').enc"
    $dialogo.OverwritePrompt = $true
    try {
        if ($dialogo.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            Write-Host "Cancelado. No se exportaron claves."
            exit 0
        }
        $Destino = $dialogo.FileName
    } finally {
        $dialogo.Dispose()
    }
}

Push-Location -LiteralPath $backend
try {
    & $python -m scripts.custodiar_claves_respaldos exportar $Destino
    if ($LASTEXITCODE -ne 0) { throw "No se pudo exportar. El archivo existente nunca se sobrescribe." }
} finally {
    Pop-Location
}

$archivo = Get-Item -LiteralPath $Destino
$raiz = [System.IO.Path]::GetPathRoot($archivo.FullName)
$unidad = New-Object System.IO.DriveInfo($raiz)
$externo = $unidad.DriveType -in @([System.IO.DriveType]::Removable, [System.IO.DriveType]::Network)
$carpetaEstado = Join-Path $env:LOCALAPPDATA "Pangea"
New-Item -ItemType Directory -Path $carpetaEstado -Force | Out-Null
$recibo = @{
    estado = "Guardado"
    fecha = (Get-Date).ToUniversalTime().ToString("o")
    destino = $archivo.FullName
    sha256 = (Get-FileHash -LiteralPath $archivo.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    ubicacion_externa_detectada = $externo
}
$recibo | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $carpetaEstado "custodia-respaldos-local.json") -Encoding UTF8
if ($externo) {
    Write-Host "Paquete guardado en unidad externa. Conserva la frase secreta por separado." -ForegroundColor Green
} else {
    Write-Host "Paquete creado. No se detecto una unidad extraible o de red: verifica que la carpeta se sincronice fuera del equipo o copia el archivo a un USB." -ForegroundColor Yellow
}
