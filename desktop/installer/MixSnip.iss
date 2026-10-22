; Inno Setup 7.1.0. Build from a clean application payload with no personal data.
#ifndef AppSource
  #define AppSource "..\dist\MixSnip"
#endif
#ifndef BuildOutput
  #define BuildOutput "..\releases"
#endif

[Setup]
AppId={{EAA66238-4C43-4828-8A19-D953D90B3A19}
AppName=MixSnip
AppVersion=0.3.0
AppPublisher=Circular-E
AppPublisherURL=https://github.com/Circular-E/MixSnip
AppSupportURL=https://github.com/Circular-E/MixSnip/issues
AppUpdatesURL=https://github.com/Circular-E/MixSnip/releases
DefaultDirName={localappdata}\Programs\MixSnip
DefaultGroupName=MixSnip
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableWelcomePage=yes
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
OutputDir={#BuildOutput}
OutputBaseFilename=MixSnip-0.3.0-Setup-x64
SetupIconFile={#AppSource}\source\assets\app.ico
UninstallDisplayIcon={app}\MixSnip.exe
Compression=lzma2/normal
SolidCompression=yes
LZMANumBlockThreads=4
LZMAUseSeparateProcess=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
Uninstallable=yes
SetupLogging=yes

[Languages]
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
zh.DesktopIcon=创建桌面快捷方式
zh.Autostart=登录 Windows 后在系统托盘启动
zh.Launch=启动 MixSnip
english.DesktopIcon=Create a desktop shortcut
english.Autostart=Start MixSnip in the tray when you sign in
english.Launch=Launch MixSnip

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: checkedonce
Name: "autostart"; Description: "{cm:Autostart}"; Flags: unchecked

[Files]
Source: "{#AppSource}\MixSnip.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppSource}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppSource}\使用说明.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppSource}\_internal\*"; DestDir: "{app}\_internal"; Excludes: "__pycache__\*,*.pyc,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\onnx\*"; DestDir: "{app}\onnx"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\formula-runtime\*"; DestDir: "{app}\formula-runtime"; Excludes: "__pycache__\*,*.pyc,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\source\*"; DestDir: "{app}\source"; Excludes: "__pycache__\*,*.pyc,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppSource}\examples\*"; DestDir: "{app}\examples"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MixSnip"; Filename: "{app}\MixSnip.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\MixSnip"; Filename: "{app}\MixSnip.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MixSnip.exe"; Parameters: "--autostart enable"; Tasks: autostart; Flags: runhidden waituntilterminated
Filename: "{app}\MixSnip.exe"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command, ExecutablePath: String;
begin
  if CurUninstallStep = usUninstall then begin
    ExecutablePath := ExpandConstant('{app}\MixSnip.exe');
    if RegQueryStringValue(HKCU, RunKey, 'MixSnip', Command) then
      if (CompareText(Command, '"' + ExecutablePath + '" --background') = 0) or
         (CompareText(Command, ExecutablePath + ' --background') = 0) then
        RegDeleteValue(HKCU, RunKey, 'MixSnip');
  end;
end;

// No UninstallDelete section: data/ is created by the app and remains after uninstall.
