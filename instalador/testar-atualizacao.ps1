#Requires -Version 7.4
# Teste da atualização automática no runner do CI (ADR-026). Máquina descartável, administrador.
# Instala N (build de teste, com chaves públicas de teste), serve N+1 por uma API falsa local em
# https://127.0.0.1 e roda o Bench com --teste-atualizacao: consulta, baixa, confere e "fecha".
# Confere versão, ApiUrl, protegido\, ACL e as recusas. Os instaladores de teste nunca são
# publicados (ajuste 7). Nunca rode numa máquina de uso.
param(
    [Parameter(Mandatory)][string]$SetupN,
    [Parameter(Mandatory)][string]$SetupN1,
    [Parameter(Mandatory)][string]$VersaoN,
    [Parameter(Mandatory)][string]$VersaoN1,
    [Parameter(Mandatory)][string]$Chaves,       # pasta com principal.key.pem e reserva.key.pem
    [Parameter(Mandatory)][securestring]$Senha
)
$ErrorActionPreference = 'Stop'
$PORTA = 8443
$URL = "https://127.0.0.1:$PORTA"
$pasta = Join-Path ${env:ProgramFiles} 'ITC\Bench'
$exe = Join-Path $pasta 'ITC Bench.exe'
$dados = Join-Path ${env:ProgramData} 'ITC\Bench'
$baixados = Join-Path $dados 'protegido\atualizacao'
$chave = 'HKLM:\SOFTWARE\ITC\Bench'
$desinstalar = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}_is1'
$logs = Join-Path ${env:RUNNER_TEMP} 'inno-logs'
$trabalho = Join-Path ${env:RUNNER_TEMP} 'atualizacao'
$servido = Join-Path $trabalho 'servido'
New-Item -ItemType Directory -Force $logs, $servido | Out-Null
$falhas = [System.Collections.Generic.List[string]]::new()
$appDir = Join-Path $PSScriptRoot '..\app'

function Conferir([string]$nome, [bool]$ok) {
    if ($ok) { Write-Host "ok    $nome" } else { Write-Host "FALHA $nome"; $falhas.Add($nome) }
}
function Instalar([string]$setup, [string]$rotulo, [string[]]$extra) {
    $argumentos = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$(Join-Path $logs "$rotulo.log")") + $extra
    (Start-Process $setup -ArgumentList $argumentos -Wait -PassThru).ExitCode
}
function Versao() { (Get-ItemProperty $desinstalar).DisplayVersion }
function Servir([string]$setup, [string]$chavePem) {
    # Manifesto assinado pelo mesmo script que o responsável usa.
    Copy-Item $setup (Join-Path $servido 'setup.exe') -Force
    $nome = Split-Path $setup -Leaf
    $sums = Join-Path $trabalho 'SHA256SUMS'
    "$((Get-FileHash $setup -Algorithm SHA256).Hash.ToLower())  $nome" | Set-Content $sums -Encoding ascii
    & (Join-Path $PSScriptRoot 'assinar-versao.ps1') -Instalador $setup -Sha256Sums $sums -Minima $VersaoN `
        -Notas 'Teste do CI.' -Chave $chavePem -Saida $servido -Senha $Senha | Out-Null
}
function Modo([string]$m) { Set-Content (Join-Path $servido 'modo.txt') $m -Encoding ascii }
function Atualizar() {
    (Start-Process $exe -ArgumentList '--teste-atualizacao' -Wait -PassThru).ExitCode
}
function Esperar([string]$versao) {
    $limite = (Get-Date).AddMinutes(4)
    while ((Versao) -ne $versao -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }
    # O instalador ainda pode estar terminando depois de gravar a versão.
    while ((Get-Process | Where-Object { $_.Name -like 'setup-*' }) -and (Get-Date) -lt $limite) { Start-Sleep 1 }
    (Versao) -eq $versao
}

# --- Certificado autoassinado para 127.0.0.1, confiado só neste runner ---
$rsa = [Security.Cryptography.RSA]::Create(2048)
$req = [Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=127.0.0.1', $rsa,
    [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
$san = [Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
$san.AddIpAddress([Net.IPAddress]::Parse('127.0.0.1'))
$req.CertificateExtensions.Add($san.Build())
$cert = $req.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5), [DateTimeOffset]::UtcNow.AddDays(1))
Set-Content (Join-Path $trabalho 'cert.pem') $cert.ExportCertificatePem() -Encoding ascii
Set-Content (Join-Path $trabalho 'chave.pem') $rsa.ExportPkcs8PrivateKeyPem() -Encoding ascii
[IO.File]::WriteAllBytes((Join-Path $trabalho 'cert.cer'), $cert.Export('Cert'))
Import-Certificate -FilePath (Join-Path $trabalho 'cert.cer') -CertStoreLocation Cert:\LocalMachine\Root | Out-Null

# Chave fora do pacote, para a recusa de assinatura.
$estranha = Join-Path $trabalho 'estranha'
& (Join-Path $PSScriptRoot 'gerar-chaves-versao.ps1') -Saida $estranha -Senha $Senha -Publicas (Join-Path $trabalho 'pub-estranha') | Out-Null

$api = Start-Process uv -ArgumentList @('--directory', $appDir, 'run', '--frozen', 'python', '-I',
    (Join-Path $PSScriptRoot 'api_falsa.py'), '--porta', $PORTA, '--cert', (Join-Path $trabalho 'cert.pem'),
    '--chave', (Join-Path $trabalho 'chave.pem'), '--pasta', $servido) -PassThru -NoNewWindow
try {
    # 1. Instala N com o endereço da API falsa.
    Conferir "instala N ($VersaoN)" ((Instalar $SetupN 'n' @("/APIURL=$URL")) -eq 0)
    New-Item -ItemType Directory -Force (Join-Path $dados 'protegido') | Out-Null
    Set-Content (Join-Path $dados 'protegido\marca.txt') 'teste'
    Start-Sleep -Seconds 3

    # 2. Recusas: DisplayVersion continua N.
    Servir $SetupN1 (Join-Path $Chaves 'principal.key.pem')
    Modo 'hash'
    Conferir 'recusa hash errado' ((Atualizar) -eq 5 -and (Versao) -eq $VersaoN)
    Modo 'redireciona'
    Conferir 'recusa redirecionamento' ((Atualizar) -eq 5 -and (Versao) -eq $VersaoN)
    Modo 'ok'
    Servir $SetupN1 (Join-Path $estranha 'principal.key.pem')
    Conferir 'recusa assinatura de chave fora do pacote' ((Atualizar) -eq 5 -and (Versao) -eq $VersaoN)
    Servir $SetupN (Join-Path $Chaves 'principal.key.pem')
    Conferir 'recusa versão igual à instalada' ((Atualizar) -eq 5 -and (Versao) -eq $VersaoN)
    Set-ItemProperty $chave ApiUrl "http://127.0.0.1:$PORTA"
    Servir $SetupN1 (Join-Path $Chaves 'principal.key.pem')
    Conferir 'recusa endereço http://' ((Atualizar) -eq 5 -and (Versao) -eq $VersaoN)
    Set-ItemProperty $chave ApiUrl $URL

    # 3. Atualiza N -> N+1 assinado pela reserva (a chave principal pode faltar).
    Servir $SetupN1 (Join-Path $Chaves 'reserva.key.pem')
    Conferir 'Bench dispara a atualização e sai' ((Atualizar) -eq 0)
    Conferir "DisplayVersion = N+1 ($VersaoN1)" (Esperar $VersaoN1)
    Conferir 'arquivo marcador do N+1 instalado' (Test-Path (Join-Path $pasta '_internal\itc_bench\recursos\atualizacao\marca-n1.txt'))
    Conferir 'ApiUrl mantido' ((Get-ItemProperty $chave).ApiUrl -eq $URL)
    Conferir 'protegido\ mantido' (Test-Path (Join-Path $dados 'protegido\marca.txt'))
    $innoLog = Get-ChildItem $baixados -Filter 'inno-*.log' | Select-Object -First 1
    Conferir 'log do Inno em protegido\atualizacao' ([bool]$innoLog)
    if ($innoLog) {
        Copy-Item $innoLog.FullName (Join-Path $logs 'atualizacao-inno.log')
        Conferir 'Inno esperou o Bench (ESPERAPID)' ((Get-Content $innoLog.FullName -Raw) -match 'ESPERAPID')
    }
    & (Join-Path $PSScriptRoot 'conferir-acl.ps1') -Pasta $pasta
    Conferir 'ACL e reparse da pasta depois da atualização' ($LASTEXITCODE -eq 0)
    $sddl = (Get-Acl $baixados).Sddl
    Conferir 'protegido\atualizacao só SY/BA' ($sddl -notmatch ';;;(BU|AU|WD|IU)\)')

    # 4. Instalador: rebaixamento recusado, igual permitido, PID de outro programa não espera.
    Conferir 'instalador recusa versão menor' ((Instalar $SetupN 'menor' @()) -ne 0 -and (Versao) -eq $VersaoN1)
    Conferir 'instalador aceita versão igual (reparo)' ((Instalar $SetupN1 'igual' @()) -eq 0)
    $outro = Start-Process ping -ArgumentList '-n', '120', '127.0.0.1' -PassThru -WindowStyle Hidden
    $inicio = Get-Date
    Conferir 'ESPERAPID de outro programa não espera' ((Instalar $SetupN1 'pid-outro' @("/ESPERAPID=$($outro.Id)")) -eq 0 -and
        ((Get-Date) - $inicio).TotalSeconds -lt 50)
    Stop-Process -Id $outro.Id -Force -ErrorAction SilentlyContinue
} finally {
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 5. Mutex: usuário comum segurando Global\ITCBench não trava a instalação.
& (Join-Path $PSScriptRoot 'prova-mutex.ps1') -Nome 'Global\ITCBench' -Instalar {
    (Instalar $SetupN1 'mutex-alheio' @()) -eq 0
}
Conferir 'mutex de usuário comum não trava o instalador' ($LASTEXITCODE -eq 0)

# 6. Desinstala.
Start-Process (Join-Path $pasta 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
$limite = (Get-Date).AddMinutes(3)
while ((Test-Path $desinstalar) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 2 }

if ($falhas.Count) { throw "$($falhas.Count) falha(s): $($falhas -join '; ')" }
Write-Host 'Atualização: todas as conferências passaram.'
