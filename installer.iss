; Inno Setup 6.3+ script. Compiled by build.bat after PyInstaller.
#define AppVer "0.2.0"

[Setup]
AppId={{7B0C6E52-3A4F-4D1B-9E57-2C8A61F0B3D9}
AppName=BiTT Assistant
AppVersion={#AppVer}
AppPublisher=Miit Edu Tools
AppPublisherURL=https://miitedu.tools
DefaultDirName={autopf}\BiTT Assistant
DefaultGroupName=BiTT Assistant
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=BittAssistant-Setup
SetupIconFile=assets\bitt.ico
UninstallDisplayIcon={app}\BittAssistant.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\BittAssistant\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\BiTT Assistant"; Filename: "{app}\BittAssistant.exe"
Name: "{autodesktop}\BiTT Assistant"; Filename: "{app}\BittAssistant.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BittAssistant.exe"; Description: "{cm:LaunchProgram,BiTT Assistant}"; Flags: nowait postinstall skipifsilent
