# Grava ou apaga os valores de um alvo (ADR-021). $env:ITC_HIVE; $env:ITC_OPERACOES =
# [{p, chave, nome, tipo, dado, acao, lista}], montado só do catálogo. Uma linha por operação.
Hive-Escrita $env:ITC_HIVE
# PS 5.1: ConvertFrom-Json devolve o array como um objeto só; ForEach-Object desenrola.
$ops = @($env:ITC_OPERACOES | ConvertFrom-Json | ForEach-Object { $_ })
foreach ($o in $ops) {
    if (-not (Raiz-Aceita $env:ITC_HIVE $o.chave)) { Falhar 'raiz' }
    if ($o.acao -notin @('gravar', 'apagar', 'apagar_se_igual', 'apagar_se_vazia')) { Falhar 'acao' }
    if ($o.tipo -notin @('dword', 'sz')) { Falhar 'tipo' }
}
$base = Base $env:ITC_HIVE

function Abrir-Criando($base, [string]$chave) {
    $atual = $base
    $nova = $true
    foreach ($parte in $chave.Split('\')) {
        $k = $atual.OpenSubKey($parte, $true)
        if (-not $k) {
            if ($nova) {
                # Primeira chave que falta: ACL explícita, dono Administradores; as de baixo herdam.
                $sec = New-Object Security.AccessControl.RegistrySecurity
                $sec.SetSecurityDescriptorSddlForm($SDDL_NOVA)
                $k = $atual.CreateSubKey($parte, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, $sec)
                $nova = $false
            } else { $k = $atual.CreateSubKey($parte, $true) }
        }
        if ($atual -ne $base) { $atual.Close() }
        $atual = $k
    }
    return $atual
}

foreach ($o in $ops) {
    try {
        if ($o.acao -eq 'gravar') {
            $k = Abrir-Criando $base $o.chave
            if ($o.tipo -eq 'dword') { $k.SetValue($o.nome, [int]$o.dado, 'DWord') }
            else { $k.SetValue($o.nome, [string]$o.dado, 'String') }
            $k.Close()
        } else {
            $k = $base.OpenSubKey($o.chave, $true)
            if ($k) {
                $atual = $k.GetValue($o.nome, $null, 'DoNotExpandEnvironmentNames')
                $apagar = $null -ne $atual
                if ($o.acao -eq 'apagar_se_igual') { $apagar = $apagar -and ("$atual" -ieq [string]$o.dado) }
                if ($o.acao -eq 'apagar_se_vazia') {
                    $lista = $base.OpenSubKey($o.lista, $false)
                    if ($lista) { $apagar = $apagar -and $lista.ValueCount -eq 0; $lista.Close() }
                }
                if ($apagar) { $k.DeleteValue($o.nome, $false) }
                $k.Close()
            }
        }
        Write-Output ('OK|' + $o.p)
    } catch {
        Write-Output ('ERRO|' + $_.Exception.GetType().Name + '|' + $o.p)
    }
}
$base.Close()
