$nome = $env:ITC_NOME
if (Get-LocalUser -Name $nome -ErrorAction SilentlyContinue) { Falhar 'nome_existe' $nome }
if (Get-LocalGroup -Name $nome -ErrorAction SilentlyContinue) { Falhar 'nome_grupo' $nome }
if ($nome -ieq [Environment]::MachineName -and $env:ITC_PERMITIR_NOME_PC -ne '1') { Falhar 'nome_computador' $nome }
if ($PROTEGIDAS -contains $nome) { Falhar 'suporte' $nome }
if ($RESTRITAS -contains $nome) { Falhar 'restrita' $nome }
$p = @{ Name = $nome; FullName = $nome; AccountNeverExpires = $true }
if ($env:ITC_SENHA) { $p.Password = ConvertTo-SecureString $env:ITC_SENHA -AsPlainText -Force } else { $p.NoPassword = $true }
try { New-LocalUser @p | Out-Null } catch { Falhar 'criar' $_.Exception.Message }
try {
    $novo = Get-LocalUser -Name $nome
    if ($env:ITC_NUNCA_EXPIRA -eq '1') { Set-LocalUser -SID $novo.SID -PasswordNeverExpires $true }
    Garantir-Membro $SID_USR $novo
    if ($env:ITC_TIPO -eq 'admin') { Garantir-Membro $SID_ADM $novo }
    if ($env:ITC_CLONAR) {
        foreach ($g in @(Get-LocalGroup)) {
            if ($g.SID.Value -in @($SID_ADM, $SID_USR)) { continue }
            try { $dentro = @(Get-LocalGroupMember -SID $g.SID | Where-Object { $_.SID.Value -eq $env:ITC_CLONAR }) }
            catch { Write-Output ('AVISO|grupo|' + $g.Name + ': ' + $_.Exception.Message); continue }
            if ($dentro) { Garantir-Membro $g.SID.Value $novo; Write-Output ('GRUPO|' + $g.Name) }
        }
    }
} catch { Falhar 'parcial' $_.Exception.Message }
# Sem a animação do primeiro logon ("Olá"...) em contas novas (ADR-051); valor da máquina.
# Falha não desfaz a conta: vira aviso.
try {
    $sis = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
    if (-not (Test-Path $sis)) { New-Item -Path $sis -Force | Out-Null }
    New-ItemProperty -Path $sis -Name 'EnableFirstLogonAnimation' -PropertyType DWord -Value 0 -Force | Out-Null
} catch { Write-Output ('AVISO|animacao|Animação do primeiro logon não desligada: ' + $_.Exception.Message) }
# Sem a tela de privacidade no primeiro logon e com as respostas já dadas (ADR-054): localização
# sim; diagnóstico opcional, escrita à tinta e digitação, ID de anúncio e Localizar meu
# dispositivo não. Valores fixos da máquina; falha vira aviso.
$PRIVACIDADE = @(
    @('HKLM:\SOFTWARE\Policies\Microsoft\Windows\OOBE', 'DisablePrivacyExperience', 1),
    @('HKLM:\SOFTWARE\Policies\Microsoft\Windows\DataCollection', 'AllowTelemetry', 1),
    @('HKLM:\SOFTWARE\Policies\Microsoft\InputPersonalization', 'AllowInputPersonalization', 0),
    @('HKLM:\SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo', 'DisabledByGroupPolicy', 1),
    @('HKLM:\SOFTWARE\Policies\Microsoft\FindMyDevice', 'AllowFindMyDevice', 0)
)
$falhas = @()
foreach ($v in $PRIVACIDADE) {
    try {
        if (-not (Test-Path $v[0])) { New-Item -Path $v[0] -Force | Out-Null }
        New-ItemProperty -Path $v[0] -Name $v[1] -PropertyType DWord -Value $v[2] -Force | Out-Null
    } catch { $falhas += $v[1] }
}
try {
    $loc = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location'
    if (-not (Test-Path $loc)) { New-Item -Path $loc -Force | Out-Null }
    New-ItemProperty -Path $loc -Name 'Value' -PropertyType String -Value 'Allow' -Force | Out-Null
} catch { $falhas += 'location' }
if ($falhas) { Write-Output ('AVISO|privacidade|Respostas de privacidade não gravadas: ' + ($falhas -join ', ')) }
# SID da conta nova, para o Bench preparar o perfil sem entrar nela (ADR-050).
Write-Output ('SID|' + $novo.SID.Value)
Write-Output 'OK'
