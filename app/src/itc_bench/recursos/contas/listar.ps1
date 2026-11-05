$admins = Membros-Admin
$logados = Sids-Logados
$perfis = @{}
foreach ($p in @(Get-CimInstance -ClassName Win32_UserProfile)) { $perfis[$p.SID] = $p }
$todas = @(Get-LocalUser)
$contas = foreach ($u in $todas) {
    $sid = $u.SID.Value
    if ($sid -match '-(501|503|504)$') { continue }
    $p = $perfis[$sid]
    [pscustomobject]@{
        sid = $sid; nome = $u.Name; ativo = [bool]$u.Enabled; admin = [bool]($admins -contains $sid)
        fonte = "$($u.PrincipalSource)"; logada = [bool]($logados -contains $sid)
        ultima = $(if ($u.LastLogon) { $u.LastLogon.ToString('o') } else { $null })
        perfil = $(if ($p) { $p.LocalPath } else { $null }); carregado = [bool]($p -and $p.Loaded)
    }
}
$locais = @($todas | ForEach-Object { $_.SID.Value })
$outros = foreach ($s in $admins) {
    if ($locais -contains $s) { continue }
    $nome = try { (New-Object Security.Principal.SecurityIdentifier($s)).Translate([Security.Principal.NTAccount]).Value } catch { $s }
    [pscustomobject]@{ sid = $s; nome = $nome }
}
[pscustomobject]@{ contas = @($contas); outros_admins = @($outros); computador = [Environment]::MachineName } |
    ConvertTo-Json -Compress -Depth 4
