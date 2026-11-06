# Lê os valores do catálogo em cada hive pedido, o dono e a ACL da chave mais próxima (ADR-021).
# $env:ITC_LEITURA = [{hive, grupos:[sid]}]; $env:ITC_CHAVES = [{escopo, chave, nomes:[...]}].
$ESCRITA = [Security.AccessControl.RegistryRights]'SetValue, CreateSubKey, Delete, ChangePermissions, TakeOwnership'
# PS 5.1: ConvertFrom-Json devolve o array como um objeto só; ForEach-Object desenrola.
$leitura = @($env:ITC_LEITURA | ConvertFrom-Json | ForEach-Object { $_ })
$chaves = @($env:ITC_CHAVES | ConvertFrom-Json | ForEach-Object { $_ })

function Alteravel($base, [string]$chave, $grupos) {
    # Sobe até a raiz de política; a primeira chave que existir decide.
    $caminho = $chave
    while ($caminho) {
        $k = $null
        try { $k = $base.OpenSubKey($caminho, $false) } catch { return $null }
        if ($k) {
            try { $acl = $k.GetAccessControl() } catch { return $null } finally { $k.Close() }
            $dono = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
            if ($grupos -contains $dono) { return $true }
            foreach ($r in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
                if ($r.AccessControlType -eq 'Allow' -and ($r.RegistryRights -band $ESCRITA) -and
                    $grupos -contains $r.IdentityReference.Value) { return $true }
            }
            return $false
        }
        $i = $caminho.LastIndexOf('\')
        if ($i -lt 0) { return $null }
        $caminho = $caminho.Substring(0, $i)
        if ($caminho -match '^(Software|SOFTWARE)$' -or $caminho -match '\\CurrentVersion$') { return $null }
    }
    return $null
}

$hives = @{}
foreach ($l in $leitura) {
    Hive-Formato $l.hive
    $escopo = if ($l.hive -eq 'MAQUINA') { 'maquina' } else { 'usuario' }
    $grupos = @($l.grupos)
    $r = @{ ok = $true; valores = @{}; alteravel = @{} }
    try { $base = Base $l.hive } catch { $r.ok = $false; $hives[$l.hive] = $r; continue }
    foreach ($c in $chaves) {
        if ($c.escopo -ne $escopo) { continue }
        if (-not (Raiz-Aceita $l.hive $c.chave)) { Falhar 'raiz' }
        $k = $null
        try { $k = $base.OpenSubKey($c.chave, $false) } catch { $r.ok = $false }
        foreach ($n in @($c.nomes)) {
            $v = if ($k) { $k.GetValue($n, $null, 'DoNotExpandEnvironmentNames') } else { $null }
            $r.valores[$c.chave + '|' + $n] = $(if ($null -eq $v) { $null } else { "$v" })
        }
        if ($k) { $k.Close() }
        if ($escopo -eq 'usuario' -and $grupos.Count) { $r.alteravel[$c.chave] = Alteravel $base $c.chave $grupos }
    }
    $base.Close()
    $hives[$l.hive] = $r
}
$maq = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista)
$ver = $maq.OpenSubKey('SOFTWARE\Microsoft\Windows NT\CurrentVersion', $false)
[pscustomobject]@{
    edicao = "$($ver.GetValue('EditionID'))"
    dono = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    hives = $hives
} | ConvertTo-Json -Compress -Depth 5
