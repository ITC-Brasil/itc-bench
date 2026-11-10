# Senha permanente do RustDesk (ADR-031): `rustdesk.exe --password`, com o serviço rodando.
# Dados: ITC_EXE (caminho do rustdesk.exe instalado, conferido no Python) e ITC_SENHA (Sensivel).
# A senha aparece na linha de comando do rustdesk.exe só durante a chamada (risco aceito no
# ADR-031). A saída do rustdesk.exe nunca é devolvida: só OK ou ERRO|codigo.
$exe = $env:ITC_EXE
if (-not $exe -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    Write-Output 'ERRO|exe'
    exit 2
}
if (-not $env:ITC_SENHA) {
    Write-Output 'ERRO|senha_vazia'
    exit 2
}
# O rustdesk.exe é um programa de janela: o pipe faz o PowerShell esperar ele terminar.
& $exe --password $env:ITC_SENHA 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Output ('ERRO|codigo|' + $LASTEXITCODE)
    exit 3
}
Write-Output 'OK'
