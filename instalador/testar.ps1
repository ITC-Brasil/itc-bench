# Teste do instalador no runner do CI (administrador, máquina descartável). ADR-025.
# Instala, confere, atualiza por cima, desinstala e confere o que sobra. Nunca rode numa máquina
# de uso: apaga %ProgramData%\ITC\Bench\protegido e mexe em HKLM\SOFTWARE\ITC\Bench.
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [Parameter(Mandatory = $true)][string]$Versao
)
$ErrorActionPreference = 'Stop'
$URL = 'https://api.exemplo.invalid'
$pasta = Join-Path ${env:ProgramFiles} 'ITC\Bench'
$exe = Join-Path $pasta 'ITC Bench.exe'
$dados = Join-Path ${env:ProgramData} 'ITC\Bench'
$chave = 'HKLM:\SOFTWARE\ITC\Bench'
$desinstalar = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}_is1'
$logs = Join-Path ${env:RUNNER_TEMP} 'inno-logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$falhas = [System.Collections.Generic.List[string]]::new()

function Conferir([string]$nome, [bool]$ok) {
    if ($ok) { Write-Host "ok    $nome" } else { Write-Host "FALHA $nome"; $falhas.Add($nome) }
}

function Instalar([string]$rotulo, [string[]]$extra) {
    $log = Join-Path $logs "$rotulo.log"
    $argumentos = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$log") + $extra
    (Start-Process $Setup -ArgumentList $argumentos -Wait -PassThru).ExitCode
}

function Bench([string[]]$argumentos) {
    (Start-Process $exe -ArgumentList $argumentos -Wait -PassThru).ExitCode
}

# 1. Recusas antes de instalar.
Conferir 'silenciosa nova sem /APIURL falha' ((Instalar 'sem-url' @()) -ne 0)
foreach ($ruim in @('http://api.exemplo.invalid', 'https://u:s@api.exemplo.invalid',
        'https://api.exemplo.invalid/?q=1', 'https://api.exemplo.invalid/#f', 'https://')) {
    Conferir "recusa $ruim" ((Instalar 'recusa' @("/APIURL=$ruim")) -ne 0)
}
Conferir 'nada instalado depois das recusas' (-not (Test-Path $pasta))

# 2. Instalação.
Conferir 'instalação silenciosa' ((Instalar 'instalar' @("/APIURL=$URL")) -eq 0)
Conferir 'EXE na pasta fixa' (Test-Path $exe)
$fonte = Join-Path $PSScriptRoot '..\app\src\itc_bench\recursos'
$contar = { param($p) (Get-ChildItem $p -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' }).Count }
Conferir 'recursos completos' ((& $contar (Join-Path $pasta '_internal\itc_bench\recursos')) -eq (& $contar $fonte))
# Árvore instalada = conteúdo do instalador descomprimido (o LZMA do Inno esconde de `strings`).
& uv --directory (Join-Path $PSScriptRoot '..\app') run --frozen --group build python ../instalador/varrer.py $pasta
Conferir 'varredura da árvore instalada' ($LASTEXITCODE -eq 0)
Conferir 'atalho só no Menu Iniciar' ((Test-Path "${env:ProgramData}\Microsoft\Windows\Start Menu\Programs\ITC Bench.lnk") -and
    -not (Test-Path "${env:PUBLIC}\Desktop\ITC Bench.lnk"))

# 3. ACL e reparse da pasta (conferir-acl.ps1).
& (Join-Path $PSScriptRoot 'conferir-acl.ps1') -Pasta $pasta
Conferir 'ACL sem escrita de terceiros e sem ponto de reparse' ($LASTEXITCODE -eq 0)

# 4. Versão e registro.
Conferir "versão do EXE = $Versao" ((Get-Item $exe).VersionInfo.ProductVersion -eq $Versao)
$registro = Get-ItemProperty $desinstalar
Conferir 'DisplayVersion' ($registro.DisplayVersion -eq $Versao)
Conferir 'InstallLocation' ($registro.InstallLocation.TrimEnd('\') -eq $pasta)
Conferir 'ApiUrl gravado' ((Get-ItemProperty $chave).ApiUrl -eq $URL)

# 5. O app empacotado: --teste confere a pasta e lê todos os recursos; variáveis hostis ignoradas.
$env:PYTHONPATH = 'C:\naoexiste'; $env:QT_QPA_PLATFORM_PLUGIN_PATH = 'C:\naoexiste'
$env:QT_PLUGIN_PATH = 'C:\naoexiste'
$codigo = Bench @('--teste')
Remove-Item Env:PYTHONPATH, Env:QT_QPA_PLATFORM_PLUGIN_PATH, Env:QT_PLUGIN_PATH
$log = Get-Content (Join-Path $dados 'logs\bench.log') -Encoding UTF8 -Tail 20
Conferir 'ITC Bench.exe --teste = 0' ($codigo -eq 0)
Conferir 'log com a versão' ([bool]($log -match "ITC Bench $([regex]::Escape($Versao)) iniciado"))
Conferir 'log: recursos lidos' ([bool]($log -match 'Recursos: \d+ arquivos lidos'))
Conferir 'log: ambiente do usuário ignorado' ([bool]($log -match 'ignoradas: .*PYTHONPATH'))
Conferir '--teste não aplicou ACL (só leitura)' ([bool]($log -match 'admin=False'))
# Pacote distribuível: --teste-atualizacao recusa (sem marcador da cópia de teste) mesmo com sessão.
$env:ITC_BENCH_SESSAO_TESTE = 'itcts_' + [guid]::NewGuid().ToString('N')
$codigo = Bench @('--teste-atualizacao')
Remove-Item Env:ITC_BENCH_SESSAO_TESTE
$log = Get-Content (Join-Path $dados 'logs\bench.log') -Encoding UTF8 -Tail 5
Conferir 'pacote: --teste-atualizacao recusa (5)' ($codigo -eq 5 -and [bool]($log -match 'não é a cópia de teste'))

# 6. Com o Bench (elevado) aberto, a atualização silenciosa recusa pelo mutex de Administradores
#    (ADR-026), sem matar o processo. O runner já é administrador: abre sem UAC.
$aberto = Start-Process $exe -PassThru
Start-Sleep -Seconds 8
Conferir 'atualização com o Bench aberto recusa' ((Instalar 'aberto' @()) -ne 0)
Conferir 'Bench continua aberto' (-not $aberto.HasExited)
Stop-Process -Id $aberto.Id -Force
$aberto.WaitForExit()

# 7. Upgrade por cima, sem /APIURL: mantém endereço e protegido\, sem rodar o desinstalador.
New-Item -ItemType Directory -Force (Join-Path $dados 'protegido') | Out-Null
Set-Content (Join-Path $dados 'protegido\marca.txt') 'teste'
Conferir 'upgrade por cima' ((Instalar 'upgrade' @()) -eq 0)
Conferir 'upgrade manteve ApiUrl' ((Get-ItemProperty $chave).ApiUrl -eq $URL)
Conferir 'upgrade manteve protegido\' (Test-Path (Join-Path $dados 'protegido\marca.txt'))
Conferir 'troca do endereço reinstalando' ((Instalar 'troca' @('/APIURL=https://outra.exemplo.invalid')) -eq 0)
Conferir 'ApiUrl trocado' ((Get-ItemProperty $chave).ApiUrl -eq 'https://outra.exemplo.invalid')

# 8. Desinstalação silenciosa. O desinstalador se copia para a pasta temporária e volta na hora:
#    espera a pasta sumir.
$unins = Join-Path $pasta 'unins000.exe'
Start-Process $unins -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$(Join-Path $logs 'desinstalar.log')" -Wait
$limite = (Get-Date).AddMinutes(3)
while ((Test-Path $pasta) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
while ((Test-Path $desinstalar) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
Conferir 'pasta de instalação removida' (-not (Test-Path $pasta))
Conferir 'atalho removido' (-not (Test-Path "${env:ProgramData}\Microsoft\Windows\Start Menu\Programs\ITC Bench.lnk"))
Conferir 'chave de desinstalação removida' (-not (Test-Path $desinstalar))
Conferir 'HKLM\SOFTWARE\ITC\Bench removida' (-not (Test-Path $chave))
Conferir 'protegido\ apagado' (-not (Test-Path (Join-Path $dados 'protegido')))
Conferir 'logs\ mantido' (Test-Path (Join-Path $dados 'logs\bench.log'))
$aviso = Get-Content (Join-Path $logs 'desinstalar.log') -Raw -Encoding UTF8
Conferir 'aviso da preparação no log' ($aviso -match 'desfaz a prepara')
Write-Host "Sobrou em $dados :"
Get-ChildItem $dados -Force | ForEach-Object { Write-Host "      $($_.Name)" }

if ($falhas.Count) { throw "$($falhas.Count) falha(s): $($falhas -join '; ')" }
Write-Host 'Instalador: todas as conferências passaram.'
