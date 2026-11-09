; Instalador do ITC Bench (ADR-025). Inno Setup 6.7.4, compilado pelo instalador/build.ps1:
;   ISCC.exe /DAppVersion=X.Y.Z instalador\itc-bench.iss
; Nenhum endereço de servidor aqui: o da API chega por /APIURL=, pelo valor já gravado ou pelo
; padrão /DApiUrlPadrao= (só no build de tag, segredo do CI; ADR-027) e vai para
; HKLM\SOFTWARE\ITC\Bench\ApiUrl. Nada é extraído nem executado de {tmp}.

#ifndef AppVersion
  #error Passe /DAppVersion=X.Y.Z (versão de app/src/itc_bench/__init__.py)
#endif
; Só o teste de atualização do CI troca a pasta (cópia com chaves de teste, nunca publicada).
; ADR-027: padrão embutido só no instalador de release (validado no CI por endereco-padrao.ps1).
#ifndef ApiUrlPadrao
  #define ApiUrlPadrao ""
#endif
#ifndef DistDir
  #define DistDir "..\app\dist\ITC Bench"
#endif

[Setup]
; AppId fixo: upgrade por cima e chave de desinstalação lida pelo Módulo 16.
AppId={{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}
AppName=ITC Bench
AppVersion={#AppVersion}
AppVerName=ITC Bench {#AppVersion}
AppPublisher=Grupo ITC Brasil
VersionInfoVersion={#AppVersion}.0
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=Grupo ITC Brasil
VersionInfoDescription=Instalador do ITC Bench
; Por máquina, 64 bits, pasta fixa (o app confere que roda dela).
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\ITC\Bench
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
; Com o Bench aberto, recusa (silenciosa) ou pede para fechar (assistente): nunca mata uma
; preparação no meio. Sem AppMutex: ele só testa se o nome existe, e um usuário comum cria
; Global\ITCBench (prova no runner, ADR-026). BenchAberto() no [Code] só conta mutex de
; Administradores/SYSTEM, criado por nucleo/instalacao.py.
CloseApplications=no
RestartApplications=no
SetupLogging=yes
UninstallDisplayIcon={app}\ITC Bench.exe
UninstallDisplayName=ITC Bench
SetupIconFile=..\app\empacotamento\itc-bench.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\app\dist
OutputBaseFilename=itc-bench-{#AppVersion}-setup

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[InstallDelete]
; Upgrade: tira os arquivos da versão anterior que não existem mais no pacote.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Só no Menu Iniciar (sem atalho na Área de Trabalho Pública).
Name: "{commonprograms}\ITC Bench"; Filename: "{app}\ITC Bench.exe"

[Registry]
; HKLM\SOFTWARE só é gravável por administradores. Sai na desinstalação (decisão 5).
Root: HKLM64; Subkey: "SOFTWARE\ITC\Bench"; ValueType: string; ValueName: "ApiUrl"; ValueData: "{code:ApiUrl}"; Flags: uninsdeletekey

[Code]
const
  CHAVE = 'SOFTWARE\ITC\Bench';
  REPARSE = $400;
  INVALIDO = $FFFFFFFF;
  AVISO_PREPARACAO =
    'A desinstalação remove o ITC Bench e os dados protegidos dele (cadastros, login offline, ' +
    'diagnósticos não enviados, estado da preparação). Ela NÃO desfaz a preparação da máquina: ' +
    'contas, Wi-Fi, políticas, programas, proteção do login e aparência continuam como estão.';
  MUTEX = 'Global\ITCBench';
  CHAVE_DESINSTALAR = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{8739FD22-418B-43F7-B9B4-2FEF3E8A3A30}_is1';
  SYNCHRONIZE = $00100000;
  READ_CONTROL = $00020000;
  PROCESS_QUERY_LIMITED_INFORMATION = $1000;
  SE_KERNEL_OBJECT = 6;
  OWNER_SECURITY_INFORMATION = 1;
  WIN_LOCAL_SYSTEM = 22;
  WIN_BUILTIN_ADMINISTRATORS = 26;
  WAIT_OBJECT_0 = 0;
  ESPERA_MS = 60000;

var
  Pagina: TInputQueryWizardPage;
  Endereco: String;

function GetFileAttributesW(Caminho: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function OpenMutexW(Acesso: Cardinal; Herdar: BOOL; Nome: String): THandle;
  external 'OpenMutexW@kernel32.dll stdcall';
function OpenProcess(Acesso: Cardinal; Herdar: BOOL; Pid: Cardinal): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function QueryFullProcessImageNameW(Processo: THandle; Flags: Cardinal; Nome: String; var Tamanho: Cardinal): BOOL;
  external 'QueryFullProcessImageNameW@kernel32.dll stdcall';
function WaitForSingleObject(Objeto: THandle; Ms: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Objeto: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';
function LocalFree(Memoria: Cardinal): Cardinal;
  external 'LocalFree@kernel32.dll stdcall';
function GetSecurityInfo(Objeto: THandle; Tipo: Integer; Info: Cardinal; var Dono: Cardinal;
  Grupo, Dacl, Sacl: Cardinal; var Descritor: Cardinal): Cardinal;
  external 'GetSecurityInfo@advapi32.dll stdcall';
function IsWellKnownSid(Sid: Cardinal; Tipo: Integer): BOOL;
  external 'IsWellKnownSid@advapi32.dll stdcall';

{ Bench elevado aberto: o mutex abre com READ_CONTROL e o dono é Administradores ou SYSTEM.
  Mutex de usuário comum é ignorado com log. Mesma regra de mutex_de_administrador() em
  nucleo/instalacao.py. }
function BenchAberto(): Boolean;
var
  H: THandle;
  Dono, Descritor: Cardinal;
begin
  Result := False;
  H := OpenMutexW(SYNCHRONIZE or READ_CONTROL, False, MUTEX);
  if H = 0 then Exit;
  try
    Dono := 0;
    Descritor := 0;
    if GetSecurityInfo(H, SE_KERNEL_OBJECT, OWNER_SECURITY_INFORMATION, Dono, 0, 0, 0, Descritor) = 0 then begin
      Result := IsWellKnownSid(Dono, WIN_BUILTIN_ADMINISTRATORS) or IsWellKnownSid(Dono, WIN_LOCAL_SYSTEM);
      LocalFree(Descritor);
    end;
    if not Result then Log('Mutex do Bench de outro usuário: ignorado.');
  finally
    CloseHandle(H);
  end;
end;

{ /ESPERAPID=<pid> (atualização ao fechar): espera o Bench sair, até 60 s. Só espera se o PID
  ainda for o ITC Bench.exe da pasta fixa; PID reaproveitado por outro programa = o Bench já
  saiu. }
function EsperouBench(): Boolean;
var
  Pid, Tamanho: Cardinal;
  H: THandle;
  Nome: String;
begin
  Result := True;
  Pid := StrToIntDef(ExpandConstant('{param:ESPERAPID|0}'), 0);
  if Pid = 0 then Exit;
  H := OpenProcess(SYNCHRONIZE or PROCESS_QUERY_LIMITED_INFORMATION, False, Pid);
  if H = 0 then begin
    Log('ESPERAPID: processo já encerrado.');
    Exit;
  end;
  try
    Tamanho := 1024;
    Nome := StringOfChar(' ', Tamanho);
    if not QueryFullProcessImageNameW(H, 0, Nome, Tamanho) then Exit;
    Nome := Copy(Nome, 1, Tamanho);
    if CompareText(Nome, ExpandConstant('{autopf}\ITC\Bench\ITC Bench.exe')) <> 0 then begin
      Log('ESPERAPID: o PID é de outro programa; o Bench já saiu.');
      Exit;
    end;
    Log('ESPERAPID: esperando o Bench sair.');
    Result := WaitForSingleObject(H, ESPERA_MS) = WAIT_OBJECT_0;
    if not Result then Log('Recusado: o Bench não saiu em 60 s.');
  finally
    CloseHandle(H);
  end;
end;

{ X.Y.Z em número comparável; -1 fora do formato. }
function VersaoNumero(V: String): Integer;
var
  I, Parte, Partes: Integer;
begin
  Result := 0;
  Parte := 0;
  Partes := 0;
  V := V + '.';
  for I := 1 to Length(V) do
    if V[I] = '.' then begin
      Result := Result * 1000 + Parte;
      Parte := 0;
      Partes := Partes + 1;
    end else if (V[I] >= '0') and (V[I] <= '9') and (Parte < 100) then
      Parte := Parte * 10 + Ord(V[I]) - Ord('0')
    else begin
      Result := -1;
      Exit;
    end;
  if Partes <> 3 then Result := -1;
end;

{ Recusa só versão MENOR que a instalada (ajuste 5): igual fica para reparo manual; a recusa de
  igual é do app. }
function Rebaixamento(): Boolean;
var
  Instalada: String;
begin
  Result := False;
  if not RegQueryStringValue(HKLM64, CHAVE_DESINSTALAR, 'DisplayVersion', Instalada) then Exit;
  Result := VersaoNumero(Instalada) > VersaoNumero('{#AppVersion}');
  if Result then Log('Recusado: a versão instalada (' + Instalada + ') é maior que {#AppVersion}.');
end;

{ Mesma regra de servicos/api.py validar(): https://, host, sem credencial, query, fragmento
  nem espaço. }
function EnderecoValido(Url: String): Boolean;
var
  Resto, Host: String;
  I, Barra: Integer;
begin
  Result := False;
  if CompareText(Copy(Url, 1, 8), 'https://') <> 0 then Exit;
  Resto := Copy(Url, 9, Length(Url));
  for I := 1 to Length(Url) do
    if (Ord(Url[I]) <= 32) or (Url[I] = '@') or (Url[I] = '?') or (Url[I] = '#') or (Url[I] = '\') then Exit;
  Barra := Pos('/', Resto);
  if Barra = 0 then Host := Resto else Host := Copy(Resto, 1, Barra - 1);
  Result := (Host <> '') and (Host[1] <> ':');
end;

function EnderecoAtual(): String;
begin
  if not RegQueryStringValue(HKLM64, CHAVE, 'ApiUrl', Result) then Result := '';
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if Rebaixamento() then begin
    if not WizardSilent() then
      MsgBox('Já existe uma versão mais nova do ITC Bench instalada.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  if not EsperouBench() then begin
    Result := False;
    Exit;
  end;
  if WizardSilent() and BenchAberto() then begin
    Log('Recusado: o ITC Bench está aberto.');
    Result := False;
    Exit;
  end;
  Endereco := Trim(ExpandConstant('{param:APIURL|}'));
  if Endereco = '' then Endereco := EnderecoAtual();
  { ADR-027: /APIURL > valor gravado (upgrade mantém) > padrão embutido no release. }
  if Endereco = '' then Endereco := '{#ApiUrlPadrao}';
  if not WizardSilent() then Exit;
  { Silenciosa: instalação nova exige /APIURL ou padrão embutido; atualização mantém o valor
    gravado. O endereço
    entra no log do Inno pela linha de comando (não é segredo; ADR-025). }
  if Endereco = '' then begin
    Log('Recusado: instalação silenciosa sem /APIURL, sem endereço gravado e sem padrão.');
    Result := False;
  end else if not EnderecoValido(Endereco) then begin
    Log('Recusado: o endereço precisa ser https:// com host, sem usuário, senha, query ou fragmento.');
    Result := False;
  end;
end;

procedure InitializeWizard();
begin
  Pagina := CreateInputQueryPage(wpWelcome, 'Endereço da API',
    'Servidor do ITC Bench',
    'Informe o endereço da API (https://...). Ele fica gravado nesta máquina e pode ser trocado ' +
    'depois rodando este instalador de novo.');
  Pagina.Add('Endereço:', False);
  Pagina.Values[0] := Endereco;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (Pagina <> nil) and (CurPageID = Pagina.ID) then begin
    Endereco := Trim(Pagina.Values[0]);
    if not EnderecoValido(Endereco) then begin
      MsgBox('Endereço inválido. Use https:// com o nome do servidor, sem usuário, senha, ' +
        'query ou fragmento.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ De novo antes de copiar: outro Bench pode ter aberto depois do InitializeSetup. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if BenchAberto() then begin
    Log('Recusado: o ITC Bench está aberto.');
    Result := 'Feche o ITC Bench e tente de novo.';
  end;
end;

function ApiUrl(Param: String): String;
begin
  Result := Endereco;
end;

{ ProgramData pelo HKLM, sem o ambiente do usuário (ADR-024). }
function DadosDoBench(): String;
var
  Valor: String;
begin
  Result := '';
  if not RegQueryStringValue(HKLM64,
    'SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList', 'ProgramData', Valor) then Exit;
  StringChangeEx(Valor, '%SystemDrive%', Copy(ExpandConstant('{win}'), 1, 2), True);
  if (Pos('%', Valor) > 0) or (Copy(Valor, 2, 2) <> ':\') then Exit;
  Result := AddBackslash(Valor) + 'ITC\Bench';
end;

function EhReparse(Caminho: String): Boolean;
var
  Atributos: Cardinal;
begin
  Atributos := GetFileAttributesW(Caminho);
  Result := (Atributos <> INVALIDO) and ((Atributos and REPARSE) <> 0);
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if UninstallSilent() then
    Log(AVISO_PREPARACAO)
  else
    Result := MsgBox(AVISO_PREPARACAO + #13#10#13#10 + 'Continuar?', mbConfirmation, MB_YESNO) = IDYES;
end;

{ Decisão 5 (b): apaga protegido\ (segredos); mantém logs\, papel\ e icones\, que a preparação
  aplicada usa. Nunca segue link: recusa se a pasta ou um pai for ponto de reparse; o
  RedirectionGuard do Inno barra junction criada por não administrador. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dados, Protegido: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  Dados := DadosDoBench();
  if Dados = '' then begin
    Log('ProgramData fora do esperado; protegido\ não apagado.');
    Exit;
  end;
  Protegido := Dados + '\protegido';
  if not DirExists(Protegido) then Exit;
  if EhReparse(ExtractFileDir(Dados)) or EhReparse(Dados) or EhReparse(Protegido) then begin
    Log('Ponto de reparse no caminho de protegido\; nada apagado.');
    Exit;
  end;
  if DelTree(Protegido, True, True, True) then
    Log('protegido\ apagado.')
  else
    Log('protegido\ não pôde ser apagado por inteiro.');
end;
