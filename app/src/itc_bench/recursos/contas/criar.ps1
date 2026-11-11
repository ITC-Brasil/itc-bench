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
Write-Output 'OK'
