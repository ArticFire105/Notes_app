<#
Start and stop the Windows local development services.
This script is called by the double-clickable project launcher.
It starts the backend.
It also starts the frontend in its own visible window.
The frontend builds before serving the production build.
Each child window stays open if its command fails.
The controller window remains open until Enter is pressed.
Enter stops the process trees started by this controller.
This includes reload workers and frontend child processes.
Gemini OCR runs through the backend.
The script does not read any configuration files.
It does not print environment variable contents other than these settings.
It never handles credentials.
The backend needs the existing Python environment.
The frontend needs its existing npm dependencies.
Run dependency installation before using this script.
The working directories are set explicitly for each process.
This makes double-clicking independent of the current folder.
Each process is started with a visible command window.
A unique mutex prevents accidental duplicate launches.
The mutex is scoped to the project directory.
The controller records only processes it creates.
It checks process start time before stopping a process.
This avoids stopping an unrelated reused process ID.
Close individual service windows only when troubleshooting.
The controller cannot clean up if forcibly terminated.
Service failures remain in the corresponding log window.
No database migration is performed here.
Read the README for manual setup and test commands.
#>

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# The hash avoids collisions between separate copies of this project.
$hash = [System.Security.Cryptography.SHA256]::Create()
try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant())
    $name = [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-', '')
} finally { $hash.Dispose() }
$created = $false
$mutex = [System.Threading.Mutex]::new($true, "Local\NotesApp-$name", [ref]$created)
if (-not $created) {
    Write-Host 'Notes App is already running from this folder. Use its controller window to stop it.'
    Read-Host 'Press Enter to close'
    $mutex.Dispose()
    exit 1
}

$processes = @()
function Start-ServiceWindow($directory, $command) {
    $process = Start-Process cmd.exe -WorkingDirectory $directory -ArgumentList '/k', $command -PassThru
    return @{ Id = $process.Id; StartTime = $process.StartTime }
}
try {
    $localUv = Join-Path $root '.tools\uv'
    if (Test-Path -LiteralPath (Join-Path $localUv 'uv.exe')) {
        $env:PATH = "$localUv;$env:PATH"
    }
    if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) { throw 'Install uv or add it to PATH.' }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js and npm or add them to PATH.' }
    $processes += Start-ServiceWindow $root 'title Notes App - Backend & uv run uvicorn app.main:app --reload'
    $processes += Start-ServiceWindow (Join-Path $root 'web') 'title Notes App - Frontend & npm.cmd run build && npm.cmd run start'
    Write-Host 'Notes App started.'
    Write-Host 'The service windows show their logs. Keep this controller open.'
    Read-Host 'Press Enter here to stop the services'
} catch {
    Write-Host $_.Exception.Message
    Read-Host 'Press Enter to stop any started services and close'
} finally {
    foreach ($process in $processes) {
        $current = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if ($current -and $current.StartTime -eq $process.StartTime) {
            & taskkill.exe /PID $process.Id /T /F | Out-Null
        }
    }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
