# Renomeia o computador (ADR-018). Nome só por $env:ITC_NOME; regras conferidas de novo aqui.
# Saída: `OK` ou `ERRO|codigo|mensagem`.
function Falhar([string]$codigo, [string]$mensagem) {
    Write-Output ('ERRO|' + $codigo + '|' + ($mensagem -replace '[\r\n]+', ' '))
    exit 1
}
$nome = $env:ITC_NOME
if ($nome -cnotmatch '^[A-Z0-9-]{1,15}$') { Falhar 'nome_invalido' '' }
if ((Get-CimInstance -ClassName Win32_ComputerSystem).PartOfDomain) { Falhar 'dominio' '' }
$join = 'HKLM:\SYSTEM\CurrentControlSet\Control\CloudDomainJoin\JoinInfo'
if (@(Get-ChildItem $join -ErrorAction SilentlyContinue).Count -gt 0) { Falhar 'dominio' '' }
if ((Get-LocalUser -Name $nome -ErrorAction SilentlyContinue) -or (Get-LocalGroup -Name $nome -ErrorAction SilentlyContinue)) {
    Falhar 'nome_local' ''
}
try { Rename-Computer -NewName $nome -Force -WarningAction SilentlyContinue }
catch { Falhar 'renomear' $_.Exception.Message }
Write-Output 'OK'
