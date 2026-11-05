$conta = Alvo $env:ITC_TIPO
try {
    if ($env:ITC_TIPO -eq 'admin') { Garantir-Membro $SID_ADM $conta }
    else { Garantir-Membro $SID_USR $conta; Remove-LocalGroupMember -SID $SID_ADM -Member $conta }
} catch [Microsoft.PowerShell.Commands.PrincipalNotFoundException] { }  # já não era administrador
catch { Falhar 'tipo' $_.Exception.Message }
Write-Output 'OK'
