#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{A8C91C0A-2874-4EB8-8F78-B88A635E3920}
AppName=REDMI Headphones Neo
AppVersion={#AppVersion}
AppPublisher=REDMI Neo Companion contributors
AppPublisherURL=https://github.com/iliasgws/redmi-headphones-neo-linux
DefaultDirName={localappdata}\Programs\REDMI Neo
DefaultGroupName=REDMI Headphones Neo
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=../..
OutputBaseFilename=REDMI-Neo-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\REDMI-Neo.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start headphone discovery when I sign in"; GroupDescription: "Startup:"

[Files]
Source: "..\..\windows-build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\REDMI Headphones Neo"; Filename: "{app}\REDMI-Neo.exe"
Name: "{autodesktop}\REDMI Headphones Neo"; Filename: "{app}\REDMI-Neo.exe"; Tasks: desktopicon
Name: "{userstartup}\REDMI Headphones Neo"; Filename: "{app}\REDMI-Neo.exe"; Parameters: "--background"; Tasks: startup

[Run]
Filename: "{app}\REDMI-Neo.exe"; Description: "Launch REDMI Headphones Neo"; Flags: nowait postinstall skipifsilent
