# Encerra as sessões do Windows de uma conta (ADR-036), pelo SID em ITC_SID. Nunca a sessão em
# que o Bench está rodando (este trecho roda na mesma sessão que ele). As sessões são achadas
# pelo dono do explorer.exe, como em Sids-Logados; logoff.exe por número de sessão.
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
$logoff = Join-Path ([Environment]::SystemDirectory) 'logoff.exe'
foreach ($s in $sessoes) {
    & $logoff $s
    if ($LASTEXITCODE -ne 0) { Falhar 'encerrar' ('sessão ' + $s + ', código ' + $LASTEXITCODE) }
}
Write-Output 'OK'
