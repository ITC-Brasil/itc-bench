# Energia (ADR-022): só leitura do esquema ativo, sem texto localizado.
# AC/DC: os dois últimos 0x... de `powercfg /query SCHEME_CURRENT <sub> <ajuste>` (ordem fixa AC, DC).
# Padrão do esquema: Power\User\Default\PowerSchemes, ou DefaultPowerSchemeValues. Saída: JSON.
$Vista = [Microsoft.Win32.RegistryView]::Registry64
$powercfg = Join-Path ([Environment]::GetFolderPath('System')) 'powercfg.exe'
# id -> (alias do grupo, alias do ajuste, GUID do grupo, GUID do ajuste)
$AJUSTES = [ordered]@{
    'tela' = @('SUB_VIDEO', 'VIDEOIDLE', '7516b95f-f776-4464-8c53-06167f40cc99', '3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e')
    'suspensao' = @('SUB_SLEEP', 'STANDBYIDLE', '238c9fa8-0aad-41ed-83f4-97be242c8f20', '29f6c1db-86da-48c5-9fdb-f2b67b1f44da')
    'hibernar_apos' = @('SUB_SLEEP', 'HIBERNATEIDLE', '238c9fa8-0aad-41ed-83f4-97be242c8f20', '9d7815a6-7ee4-497e-8888-515a05f02364')
    'disco' = @('SUB_DISK', 'DISKIDLE', '0012ee47-9041-4b5d-9b77-535fba8b1442', '6738e2c4-e8a5-4a42-b16a-e040e769756e')
}
$POWER = 'SYSTEM\CurrentControlSet\Control\Power'

function Powercfg([string[]]$argumentos) {
    $ErrorActionPreference = 'Continue'
    $saida = & $powercfg @argumentos 2>$null
    if ($LASTEXITCODE -ne 0) { return '' }
    return ($saida -join "`n")
}

function Indice($k, [string]$nome) {
    if (-not $k) { return $null }
    $v = $k.GetValue($nome, $null)
    if ($null -eq $v) { return $null }
    return [long]([uint32]$v)
}

$maq = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $Vista)
$esquema = ([regex]::Match((Powercfg @('/getactivescheme')), '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')).Value.ToLowerInvariant()
$saida = [ordered]@{ esquema = $esquema; ajustes = @{}; hibernacao = $null }
foreach ($id in $AJUSTES.Keys) {
    $a = $AJUSTES[$id]
    $r = @{ ac = $null; dc = $null; padrao_ac = $null; padrao_dc = $null }
    $hex = @([regex]::Matches((Powercfg @('/query', 'SCHEME_CURRENT', $a[0], $a[1])), '0x[0-9a-fA-F]{1,8}\b') | ForEach-Object { $_.Value })
    if ($hex.Count -ge 2) {
        $r.ac = [Convert]::ToInt64($hex[$hex.Count - 2].Substring(2), 16)
        $r.dc = [Convert]::ToInt64($hex[$hex.Count - 1].Substring(2), 16)
    }
    if ($esquema) {
        $k = $maq.OpenSubKey("$POWER\User\Default\PowerSchemes\$esquema\$($a[2])\$($a[3])", $false)
        if (-not $k) { $k = $maq.OpenSubKey("$POWER\PowerSettings\$($a[2])\$($a[3])\DefaultPowerSchemeValues\$esquema", $false) }
        $r.padrao_ac = Indice $k 'ACSettingIndex'
        $r.padrao_dc = Indice $k 'DCSettingIndex'
        if ($k) { $k.Close() }
    }
    $saida.ajustes[[string]$id] = $r
}
$k = $maq.OpenSubKey($POWER, $false)
if ($k) {
    $saida.hibernacao = Indice $k 'HibernateEnabled'
    if ($null -eq $saida.hibernacao) { $saida.hibernacao = Indice $k 'HibernateEnabledDefault' }
    $k.Close()
}
$maq.Close()
[pscustomobject]$saida | ConvertTo-Json -Compress -Depth 4
