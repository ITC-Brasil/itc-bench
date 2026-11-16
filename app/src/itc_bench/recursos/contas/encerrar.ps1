# Acha as sessões do Windows de uma conta (ADR-036, ADR-049), pelo SID em ITC_SID, para o Bench
# encerrar por WTSLogoffSession (nucleo/sessoes.py; o logoff.exe não existe no Windows Home).
# Nunca a sessão em que o Bench está rodando (este trecho roda na mesma sessão que ele). As
# sessões são achadas pelo dono do explorer.exe, como em Sids-Logados. Só lê: uma linha
# SESSAO|n por sessão e OK.
$sid = $env:ITC_SID
if ($sid -notmatch '^S-1-5-21-\d+-\d+-\d+-\d+$') { Falhar 'nao_encontrada' '' }
$eu = [Diagnostics.Process]::GetCurrentProcess().SessionId
$sessoes = @()
foreach ($p in @(Get-CimInstance -ClassName Win32_Process -Filter "Name='explorer.exe'")) {
    try { $r = Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid }
    catch { [Console]::Error.WriteLine('AVISO|explorer|' + $_.Exception.Message); continue }
    if ($r.Sid -eq $sid) { $sessoes += [int]$p.SessionId }
}
$sessoes = @($sessoes | Sort-Object -Unique)
if (-not $sessoes) { Falhar 'sem_sessao' '' }
if ($sessoes -contains $eu) { Falhar 'propria' '' }
foreach ($s in $sessoes) { Write-Output ('SESSAO|' + $s) }
Write-Output 'OK'
