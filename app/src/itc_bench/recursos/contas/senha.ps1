$acao = if ($env:ITC_SENHA) { 'senha' } else { 'sem_senha' }
$conta = Alvo $acao
try {
    if ($env:ITC_SENHA) {
        Set-LocalUser -SID $conta.SID -Password (ConvertTo-SecureString $env:ITC_SENHA -AsPlainText -Force)
    } else {
        # Set-LocalUser não tem "sem senha": marca UF_PASSWD_NOTREQD (0x20) e grava senha vazia.
        $adsi = [ADSI]('WinNT://./' + $conta.Name + ',user')
        $adsi.UserFlags.Value = $adsi.UserFlags.Value -bor 0x20
        $adsi.SetInfo()
        $adsi.SetPassword('')
    }
} catch { Falhar 'senha' $_.Exception.Message }
Write-Output 'OK'
