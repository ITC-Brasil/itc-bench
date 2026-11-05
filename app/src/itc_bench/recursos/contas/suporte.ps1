$nome = $env:ITC_NOME
$conta = Get-LocalUser -Name $nome -ErrorAction SilentlyContinue
$segura = ConvertTo-SecureString $env:ITC_SENHA -AsPlainText -Force
if ($conta) {
    if ($conta.SID.Value -match '-500$') { Falhar 'suporte_nativo' $nome }
    if (-not (Eh-Local $conta)) { Falhar 'microsoft' $nome }
}
try {
    if ($conta) {
        Set-LocalUser -SID $conta.SID -Password $segura -PasswordNeverExpires $true -AccountNeverExpires
        Enable-LocalUser -SID $conta.SID
        Write-Output 'ATUALIZADA'
    } else {
        New-LocalUser -Name $nome -FullName $nome -Password $segura -PasswordNeverExpires -AccountNeverExpires | Out-Null
        $conta = Get-LocalUser -Name $nome
        Write-Output 'CRIADA'
    }
    Garantir-Membro $SID_USR $conta
    Garantir-Membro $SID_ADM $conta
} catch { Falhar 'suporte' $_.Exception.Message }
Write-Output 'OK'
