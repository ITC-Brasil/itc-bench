# Funções comuns aos trechos de contas (ADR-017). Dados só por $env:ITC_*; alvo sempre por SID.
# Saída: linhas `OK`, `ERRO|codigo|mensagem`, `AVISO|...`, `MUDOU|nome`; a listagem devolve JSON.
$SID_ADM = 'S-1-5-32-544'
$SID_USR = 'S-1-5-32-545'
$PROTEGIDAS = @(if ($env:ITC_PROTEGIDAS) { $env:ITC_PROTEGIDAS -split "`n" | Where-Object { $_ } })

function Falhar([string]$codigo, [string]$mensagem) {
    Write-Output ('ERRO|' + $codigo + '|' + ($mensagem -replace '[\r\n]+', ' '))
    exit 1
}

function Membros-Admin {
    # Get-LocalGroupMember falha com SID órfão ou membro do AzureAD no grupo: cai para o ADSI.
    try { return @(Get-LocalGroupMember -SID $SID_ADM | ForEach-Object { $_.SID.Value }) }
    catch {
        [Console]::Error.WriteLine('AVISO|membros|' + $_.Exception.Message)
        $grupo = [ADSI]('WinNT://./' + (Get-LocalGroup -SID $SID_ADM).Name + ',group')
        return @($grupo.Invoke('Members') | ForEach-Object {
            $bytes = [byte[]]$_.GetType().InvokeMember('objectSid', 'GetProperty', $null, $_, $null)
            (New-Object Security.Principal.SecurityIdentifier($bytes, 0)).Value
        })
    }
}

function Sids-Logados {
    # Quem roda o Bench, quem tem explorer.exe (console, RDP, troca rápida) e o usuário do console.
    $sids = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
    foreach ($p in @(Get-CimInstance -ClassName Win32_Process -Filter "Name='explorer.exe'")) {
        try { $r = Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid; if ($r.Sid) { $sids += $r.Sid } }
        catch { [Console]::Error.WriteLine('AVISO|explorer|' + $_.Exception.Message) }
    }
    $console = (Get-CimInstance -ClassName Win32_ComputerSystem).UserName
    if ($console) {
        try { $sids += (New-Object Security.Principal.NTAccount($console)).Translate([Security.Principal.SecurityIdentifier]).Value }
        catch { [Console]::Error.WriteLine('AVISO|console|' + $_.Exception.Message) }
    }
    return @($sids | Select-Object -Unique)
}

function Garantir-Membro([string]$grupo, $conta) {
    try { Add-LocalGroupMember -SID $grupo -Member $conta }
    catch [Microsoft.PowerShell.Commands.MemberExistsException] { }  # já era membro: nada a fazer
}

function Eh-Local($conta) { return ("$($conta.PrincipalSource)" -in @('', 'Local')) }

# Mesmas regras de `recusa()` em servicos/contas.py, conferidas de novo aqui (ADR-017, item 3).
function Recusa([string]$acao, $conta, $admins, $logados) {
    $sid = $conta.SID.Value
    if ($sid -match '-500$') { return 'nativo' }
    if (-not (Eh-Local $conta)) { return 'microsoft' }
    if ($PROTEGIDAS -contains $conta.Name) { return 'suporte' }
    if ($acao -in @('padrao', 'excluir', 'senha', 'sem_senha') -and $logados -contains $sid) { return 'logada' }
    if ($acao -in @('padrao', 'excluir') -and $admins -contains $sid) {
        $outros = @(Get-LocalUser | Where-Object { $_.Enabled -and $_.SID.Value -ne $sid -and $admins -contains $_.SID.Value })
        if ($outros.Count -eq 0) { return 'ultimo_admin' }
    }
    if ($acao -eq 'excluir') {
        $perfil = Get-CimInstance -ClassName Win32_UserProfile | Where-Object { $_.SID -eq $sid }
        if ($perfil -and $perfil.Loaded) { return 'sessao_aberta' }
    }
    return $null
}

function Alvo([string]$acao) {
    $conta = Get-LocalUser -SID $env:ITC_SID -ErrorAction SilentlyContinue
    if (-not $conta) { Falhar 'nao_encontrada' 'Conta não encontrada.' }
    $motivo = Recusa $acao $conta (Membros-Admin) (Sids-Logados)
    if ($motivo) { Falhar $motivo $conta.Name }
    return $conta
}
