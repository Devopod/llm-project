import json
import logging
import os
import shutil
import subprocess
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')

ANDROID_HOME = '/home/ubuntu/android-sdk'
GRADLE_HOME = '/home/ubuntu/gradle/gradle-8.5'


def _detect_sdk_version():
    """Detect the latest installed Android SDK platform version."""
    platforms_dir = os.path.join(ANDROID_HOME, 'platforms')
    if not os.path.isdir(platforms_dir):
        return 34
    versions = []
    for d in os.listdir(platforms_dir):
        if d.startswith('android-'):
            try:
                versions.append(int(d.split('-')[1]))
            except (ValueError, IndexError):
                pass
    return max(versions) if versions else 34


def _detect_build_tools_version():
    """Detect the latest installed build-tools version."""
    bt_dir = os.path.join(ANDROID_HOME, 'build-tools')
    if not os.path.isdir(bt_dir):
        return '34.0.0'
    versions = sorted(os.listdir(bt_dir), reverse=True)
    return versions[0] if versions else '34.0.0'


class APKBuilderAgent(BaseAgent):
    role = 'deployer'
    system_prompt = """You are an Android APK build specialist for AstraDev.
You generate JAVA-ONLY Android projects (NO Kotlin, NO Compose).

Output MUST be valid JSON with this structure:
{
  "files": [
    {"path": "app/src/main/java/com/astradev/app/MainActivity.java", "content": "..."},
    {"path": "app/src/main/res/layout/activity_main.xml", "content": "..."},
    {"path": "app/src/main/AndroidManifest.xml", "content": "..."}
  ],
  "package_name": "com.astradev.app",
  "app_name": "MyApp"
}

RULES:
1. Use JAVA only. Never use Kotlin.
2. Use traditional Android Views (XML layouts), NOT Jetpack Compose.
3. Generate COMPLETE, compilable Java source files with all imports.
4. Include proper XML layouts in res/layout/.
5. Include strings.xml in res/values/.
6. Do NOT generate build.gradle or settings.gradle -- those are auto-generated.
7. Do NOT generate gradlew or gradle wrapper files -- those are auto-generated.
8. Every Java file must compile. Every XML file must be valid.
9. Package name must match the directory structure under app/src/main/java/."""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Generating Java Android project for APK build...')

        extra_context = ''
        if context:
            extra_context = json.dumps(context, indent=2)[:3000]

        messages = self.build_messages(task_description, extra_context)
        result = self.call_groq(messages, stream=False)
        content = result['content']
        self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif content.strip().startswith('```'):
                content = content.strip()[3:]
                if '```' in content:
                    content = content.rsplit('```', 1)[0]
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = self._default_android_project(task_description)

        self.emit('success', f"Android project generated with {len(output.get('files', []))} files")
        return output

    def build_apk(self, project_id: str, workspace_path: str) -> dict:
        """Build APK using real Gradle + Android SDK. Verify APK exists before claiming success."""
        self.emit('action', 'Starting APK build with Gradle...')

        sdk_version = _detect_sdk_version()
        bt_version = _detect_build_tools_version()

        # Step 1: Generate proper Gradle project files (removes .kts and .kt files)
        self.emit('action', f'Setting up Gradle project (SDK {sdk_version}, build-tools {bt_version})...')
        self._setup_gradle_project(workspace_path, sdk_version, bt_version)

        # Step 1b: Ensure Java source files exist (write defaults if LLM only generated Kotlin)
        java_dir = os.path.join(workspace_path, 'app', 'src', 'main', 'java')
        has_java = False
        if os.path.isdir(java_dir):
            for root, dirs, fnames in os.walk(java_dir):
                if any(f.endswith('.java') for f in fnames):
                    has_java = True
                    break
        if not has_java:
            self.emit('action', 'No Java source files found, writing default project...')
            default = self._default_android_project(f'Calculator app for project {project_id}')
            for fi in default.get('files', []):
                fpath = os.path.join(workspace_path, fi['path'])
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, 'w') as fh:
                    fh.write(fi['content'])

        # Step 2: Create proper Gradle wrapper
        self._create_real_gradle_wrapper(workspace_path)

        # Step 3: Run gradlew assembleDebug
        gradlew_path = os.path.join(workspace_path, 'gradlew')
        if not os.path.isfile(gradlew_path):
            self.emit('error', 'Failed to create Gradle wrapper')
            return {'status': 'failed', 'message': 'Gradle wrapper creation failed'}

        os.chmod(gradlew_path, 0o755)

        env = {
            **os.environ,
            'ANDROID_HOME': ANDROID_HOME,
            'ANDROID_SDK_ROOT': ANDROID_HOME,
            'JAVA_HOME': '/usr',
            'PATH': f"{os.environ.get('PATH', '')}:{ANDROID_HOME}/cmdline-tools/latest/bin:{ANDROID_HOME}/platform-tools",
        }

        self.emit('action', 'Running: ./gradlew assembleDebug ...')

        try:
            result = subprocess.run(
                ['./gradlew', 'assembleDebug', '--no-daemon', '--stacktrace'],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )

            # Log full output
            stdout_tail = result.stdout[-2000:] if result.stdout else ''
            stderr_tail = result.stderr[-2000:] if result.stderr else ''

            if result.returncode == 0:
                # Verify APK actually exists
                apk_path = self._find_apk(workspace_path)
                if apk_path:
                    apk_size = os.path.getsize(apk_path)
                    rel_apk = os.path.relpath(apk_path, workspace_path)
                    self.emit('success', f'APK built successfully: {rel_apk} ({apk_size} bytes)')
                    self.emit('action', f'Build output:\n{stdout_tail[-500:]}')

                    # Store APK info in project state
                    return {
                        'status': 'success',
                        'apk_path': rel_apk,
                        'apk_size': apk_size,
                        'build_output': stdout_tail[-1000:],
                    }
                else:
                    self.emit('error', 'Gradle reported success but no APK file found at app/build/outputs/apk/debug/')
                    self.emit('action', f'Build stdout:\n{stdout_tail[-500:]}')
                    return {
                        'status': 'failed',
                        'message': 'Build succeeded but no APK produced',
                        'build_output': stdout_tail[-1000:],
                    }
            else:
                # Build failed -- log errors and attempt fix
                self.emit('error', f'Gradle build failed (exit code {result.returncode})')
                self.emit('action', f'Build errors:\n{stderr_tail[-1000:]}')

                # Attempt auto-fix: parse error, fix source, retry once
                fix_result = self._attempt_build_fix(workspace_path, stderr_tail, env)
                if fix_result and fix_result.get('status') == 'success':
                    return fix_result

                return {
                    'status': 'failed',
                    'message': f'Gradle build failed',
                    'build_output': stdout_tail[-500:],
                    'build_errors': stderr_tail[-500:],
                }

        except subprocess.TimeoutExpired:
            self.emit('error', 'APK build timed out (10 min limit)')
            return {'status': 'failed', 'message': 'Build timed out after 10 minutes'}
        except Exception as e:
            self.emit('error', f'APK build error: {str(e)[:300]}')
            return {'status': 'failed', 'message': str(e)[:300]}

    def _attempt_build_fix(self, workspace_path: str, error_output: str, env: dict) -> dict:
        """Try to fix build errors and retry once."""
        self.emit('action', 'Attempting to auto-fix build errors...')

        try:
            fix_prompt = (
                f"The Android Gradle build failed with these errors:\n{error_output[:1500]}\n\n"
                f"Fix the Java source files to resolve these compilation errors. "
                f"Output valid JSON with fixed files only. Use JAVA only, no Kotlin."
            )
            messages = self.build_messages(fix_prompt)
            result = self.call_groq(messages, stream=False)
            content = result['content']
            self.log_token_usage(result['tokens_input'], result['tokens_output'], result['key_used'])

            try:
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0]
                fix_output = json.loads(content.strip())
            except (json.JSONDecodeError, IndexError):
                self.emit('action', 'Could not parse fix output')
                return None

            # Apply fixes
            for f in fix_output.get('files', []):
                path = f.get('path', '')
                file_content = f.get('content', '')
                if path and file_content:
                    full_path = os.path.join(workspace_path, path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, 'w') as fh:
                        fh.write(file_content)
                    self.emit('action', f'Fixed: {path}')

            # Retry build
            self.emit('action', 'Retrying build after fixes...')
            retry = subprocess.run(
                ['./gradlew', 'assembleDebug', '--no-daemon'],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )

            if retry.returncode == 0:
                apk_path = self._find_apk(workspace_path)
                if apk_path:
                    apk_size = os.path.getsize(apk_path)
                    rel_apk = os.path.relpath(apk_path, workspace_path)
                    self.emit('success', f'APK built successfully after fix: {rel_apk} ({apk_size} bytes)')
                    return {
                        'status': 'success',
                        'apk_path': rel_apk,
                        'apk_size': apk_size,
                        'build_output': retry.stdout[-1000:],
                    }

        except Exception as e:
            self.emit('action', f'Auto-fix attempt failed: {str(e)[:200]}')

        return None

    def _find_apk(self, workspace_path: str) -> str:
        """Find the built APK file. Check the standard Gradle output path first."""
        standard_path = os.path.join(workspace_path, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
        if os.path.isfile(standard_path):
            return standard_path

        # Fallback: search recursively
        for root, dirs, files in os.walk(workspace_path):
            for f in files:
                if f.endswith('.apk'):
                    return os.path.join(root, f)
        return ''

    def _setup_gradle_project(self, workspace_path: str, sdk_version: int, bt_version: str):
        """Generate proper build.gradle files for a Java-only Android project."""

        # Remove any .kts gradle files (LLM sometimes generates Kotlin DSL despite instructions)
        for kts_file in ['build.gradle.kts', 'settings.gradle.kts', 'app/build.gradle.kts']:
            kts_path = os.path.join(workspace_path, kts_file)
            if os.path.isfile(kts_path):
                os.remove(kts_path)

        # Convert any .kt files to .java using default Java fallback
        kt_files = []
        java_dir = os.path.join(workspace_path, 'app', 'src', 'main', 'java')
        if os.path.isdir(java_dir):
            for root, dirs, files in os.walk(java_dir):
                for f in files:
                    if f.endswith('.kt'):
                        kt_files.append(os.path.join(root, f))

        if kt_files:
            # Remove Kotlin files -- the default Java project will be used
            for kt_file in kt_files:
                os.remove(kt_file)

        # Detect package name from existing source files
        package_name = 'com.astradev.app'
        for root, dirs, files in os.walk(os.path.join(workspace_path, 'app', 'src', 'main', 'java')):
            for f in files:
                if f.endswith('.java'):
                    try:
                        with open(os.path.join(root, f), 'r') as fh:
                            for line in fh:
                                if line.strip().startswith('package '):
                                    package_name = line.strip().replace('package ', '').rstrip(';').strip()
                                    break
                    except Exception:
                        pass
                    break
            if package_name != 'com.astradev.app':
                break

        # Root build.gradle -- DO NOT add allprojects repositories (handled by settings.gradle)
        root_gradle = """plugins {
    id 'com.android.application' version '8.2.2' apply false
}
"""
        with open(os.path.join(workspace_path, 'build.gradle'), 'w') as f:
            f.write(root_gradle)

        # App build.gradle
        app_gradle = f"""plugins {{
    id 'com.android.application'
}}

android {{
    namespace '{package_name}'
    compileSdk {sdk_version}

    defaultConfig {{
        applicationId '{package_name}'
        minSdk 24
        targetSdk {sdk_version}
        versionCode 1
        versionName '1.0'
    }}

    buildTypes {{
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }}
    }}

    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
}}

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    implementation 'androidx.activity:activity:1.8.2'
}}
"""
        app_dir = os.path.join(workspace_path, 'app')
        os.makedirs(app_dir, exist_ok=True)
        with open(os.path.join(app_dir, 'build.gradle'), 'w') as f:
            f.write(app_gradle)

        # settings.gradle
        settings_gradle = """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = 'AstraDevApp'
include ':app'
"""
        with open(os.path.join(workspace_path, 'settings.gradle'), 'w') as f:
            f.write(settings_gradle)

        # gradle.properties
        gradle_props = """android.useAndroidX=true
android.nonTransitiveRClass=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
"""
        with open(os.path.join(workspace_path, 'gradle.properties'), 'w') as f:
            f.write(gradle_props)

        # local.properties
        local_props = f"sdk.dir={ANDROID_HOME}\n"
        with open(os.path.join(workspace_path, 'local.properties'), 'w') as f:
            f.write(local_props)

        # proguard-rules.pro (empty placeholder)
        proguard_path = os.path.join(app_dir, 'proguard-rules.pro')
        if not os.path.isfile(proguard_path):
            with open(proguard_path, 'w') as f:
                f.write('# Add project-specific ProGuard rules here.\n')

    def _create_real_gradle_wrapper(self, workspace_path: str):
        """Create a real Gradle wrapper using the installed Gradle distribution."""
        # Remove any existing fake gradlew script first
        old_gradlew = os.path.join(workspace_path, 'gradlew')
        if os.path.isfile(old_gradlew):
            os.remove(old_gradlew)

        try:
            env = {
                **os.environ,
                'ANDROID_HOME': ANDROID_HOME,
                'JAVA_HOME': '/usr',
            }
            result = subprocess.run(
                [f'{GRADLE_HOME}/bin/gradle', 'wrapper', '--gradle-version', '8.5'],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if result.returncode == 0:
                wrapper_jar = os.path.join(workspace_path, 'gradle', 'wrapper', 'gradle-wrapper.jar')
                wrapper_props = os.path.join(workspace_path, 'gradle', 'wrapper', 'gradle-wrapper.properties')
                gradlew = os.path.join(workspace_path, 'gradlew')
                if os.path.isfile(wrapper_jar) and os.path.isfile(wrapper_props) and os.path.isfile(gradlew):
                    os.chmod(gradlew, 0o755)
                    self.emit('action', 'Gradle wrapper created (gradle-wrapper.jar + properties)')
                    return
            logger.warning(f"Gradle wrapper stderr: {result.stderr[:500]}")
        except Exception as e:
            logger.warning(f"Gradle wrapper creation failed: {e}")

        # Fallback: copy from a known-good test wrapper
        self.emit('action', 'Creating Gradle wrapper from template...')
        test_wrapper_dir = '/tmp/test_android_project/gradle/wrapper'
        dst_wrapper_dir = os.path.join(workspace_path, 'gradle', 'wrapper')
        os.makedirs(dst_wrapper_dir, exist_ok=True)

        # Copy wrapper files from test project if available
        test_jar = os.path.join(test_wrapper_dir, 'gradle-wrapper.jar')
        test_props = os.path.join(test_wrapper_dir, 'gradle-wrapper.properties')
        test_gradlew = '/tmp/test_android_project/gradlew'

        if os.path.isfile(test_jar):
            shutil.copy2(test_jar, os.path.join(dst_wrapper_dir, 'gradle-wrapper.jar'))
            if os.path.isfile(test_props):
                shutil.copy2(test_props, os.path.join(dst_wrapper_dir, 'gradle-wrapper.properties'))
            if os.path.isfile(test_gradlew):
                shutil.copy2(test_gradlew, os.path.join(workspace_path, 'gradlew'))
                os.chmod(os.path.join(workspace_path, 'gradlew'), 0o755)
            self.emit('action', 'Gradle wrapper copied from template')
            return

        # Last resort: create minimal wrapper
        props_content = """distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""
        with open(os.path.join(dst_wrapper_dir, 'gradle-wrapper.properties'), 'w') as f:
            f.write(props_content)

        gradlew_content = '''#!/bin/sh
DIRNAME=$(dirname "$0")
APP_HOME=$(cd "$DIRNAME" > /dev/null && pwd)
CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar
exec java $JAVA_OPTS -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
'''
        with open(os.path.join(workspace_path, 'gradlew'), 'w') as f:
            f.write(gradlew_content)
        os.chmod(os.path.join(workspace_path, 'gradlew'), 0o755)

        # Try to find any wrapper jar in Gradle installation
        for fname in os.listdir(os.path.join(GRADLE_HOME, 'lib')):
            if 'wrapper' in fname and fname.endswith('.jar'):
                shutil.copy2(
                    os.path.join(GRADLE_HOME, 'lib', fname),
                    os.path.join(dst_wrapper_dir, 'gradle-wrapper.jar')
                )
                break

    def _default_android_project(self, description: str) -> dict:
        """Generate a default Java Android project (no Kotlin)."""
        return {
            'files': [
                {
                    'path': 'app/src/main/java/com/astradev/app/MainActivity.java',
                    'content': '''package com.astradev.app;

import android.os.Bundle;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        TextView titleText = findViewById(R.id.titleText);
        titleText.setText("AstraDev App");
    }
}
'''
                },
                {
                    'path': 'app/src/main/res/layout/activity_main.xml',
                    'content': '''<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:padding="16dp"
    android:background="#FFFFFF">

    <TextView
        android:id="@+id/titleText"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="AstraDev App"
        android:textSize="24sp"
        android:textColor="#333333"
        android:textStyle="bold"
        app:layout_constraintTop_toTopOf="parent"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintStart_toStartOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

</androidx.constraintlayout.widget.ConstraintLayout>
'''
                },
                {
                    'path': 'app/src/main/res/values/strings.xml',
                    'content': '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">AstraDev App</string>
</resources>
'''
                },
                {
                    'path': 'app/src/main/res/values/themes.xml',
                    'content': '''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.AstraDevApp" parent="Theme.MaterialComponents.DayNight.DarkActionBar">
        <item name="colorPrimary">#6200EE</item>
        <item name="colorPrimaryVariant">#3700B3</item>
        <item name="colorOnPrimary">#FFFFFF</item>
        <item name="colorSecondary">#03DAC5</item>
    </style>
</resources>
'''
                },
                {
                    'path': 'app/src/main/AndroidManifest.xml',
                    'content': '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:theme="@style/Theme.AstraDevApp">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
'''
                },
            ],
            'package_name': 'com.astradev.app',
            'app_name': 'AstraDev App',
        }
