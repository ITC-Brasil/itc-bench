; Instalador do ITC Bench (ADR-025). Inno Setup 6.7.4, compilado pelo instalador/build.ps1:
;   ISCC.exe /DAppVersion=X.Y.Z instalador\itc-bench.iss
; Nenhum endereço de servidor aqui: o da API chega na instalação (/APIURL= ou página do assistente)
; e vai para HKLM\SOFTWARE\ITC\Bench\ApiUrl. Nada é extraído nem executado de {tmp}.

#ifndef AppVersion
  #error Passe /DAppVersion=X.Y.Z (versão de app/src/itc_bench/__init__.py)
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
; preparação no meio. Mutex criado por nucleo/instalacao.py.
AppMutex=ITCBench,Global\ITCBench
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
Source: "..\app\dist\ITC Bench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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

var
  Pagina: TInputQueryWizardPage;
  Endereco: String;

function GetFileAttributesW(Caminho: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

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
  Endereco := Trim(ExpandConstant('{param:APIURL|}'));
  if Endereco = '' then Endereco := EnderecoAtual();
  if not WizardSilent() then Exit;
  { Silenciosa: instalação nova exige /APIURL; atualização mantém o valor gravado. O endereço
    entra no log do Inno pela linha de comando (não é segredo; ADR-025). }
  if Endereco = '' then begin
    Log('Recusado: instalação silenciosa sem /APIURL e sem endereço gravado.');
    Result := False;
  end else if not EnderecoValido(Endereco) then begin
    Log('Recusado: /APIURL precisa ser https:// com host, sem usuário, senha, query ou fragmento.');
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
