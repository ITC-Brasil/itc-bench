$conta = Alvo 'excluir'
$sid = $conta.SID.Value
$perfil = Get-CimInstance -ClassName Win32_UserProfile | Where-Object { $_.SID -eq $sid }
try { Remove-LocalUser -SID $conta.SID } catch { Falhar 'excluir' $_.Exception.Message }
Write-Output 'CONTA'
if ($env:ITC_PERFIL -eq '1' -and $perfil) {
    try { Remove-CimInstance -InputObject $perfil; Write-Output 'PERFIL' }
    catch { Write-Output ('AVISO|perfil|' + $_.Exception.Message) }
}
Write-Output 'OK'
