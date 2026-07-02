import json
import logging
import os
import subprocess
from .base import BaseAgent

logger = logging.getLogger('astradev.agents')


class APKBuilderAgent(BaseAgent):
    role = 'deployer'
    system_prompt = """You are an Android APK build specialist for AstraDev.
When asked to build an APK, generate a complete Android project structure with:
- Kotlin source files using Jetpack Compose
- build.gradle.kts (project-level and app-level)
- settings.gradle.kts
- AndroidManifest.xml
- gradle.properties

Output MUST be valid JSON:
{
  "files": [
    {"path": "app/src/main/java/com/astradev/app/MainActivity.kt", "content": "..."},
    {"path": "app/build.gradle.kts", "content": "..."},
    {"path": "build.gradle.kts", "content": "..."},
    {"path": "settings.gradle.kts", "content": "..."},
    {"path": "app/src/main/AndroidManifest.xml", "content": "..."},
    {"path": "gradle.properties", "content": "..."}
  ],
  "package_name": "com.astradev.app",
  "app_name": "MyApp",
  "min_sdk": 24,
  "target_sdk": 34
}

Create a COMPLETE, compilable Android project. The app should be functional
based on the user's requirements."""

    def execute(self, task_description: str, context: dict = None) -> dict:
        self.emit('action', 'Generating Android project for APK build...')

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
            output = json.loads(content.strip())
        except (json.JSONDecodeError, IndexError):
            output = self._default_android_project(task_description)

        self.emit('success', f"Android project generated with {len(output.get('files', []))} files")
        return output

    def build_apk(self, project_id: str, workspace_path: str) -> dict:
        """Attempt to build APK using gradle wrapper if available."""
        self.emit('deployment', 'Attempting APK build...')

        gradlew_path = os.path.join(workspace_path, 'gradlew')
        if not os.path.exists(gradlew_path):
            # Create gradle wrapper
            self._create_gradle_wrapper(workspace_path)

        if os.path.exists(gradlew_path):
            os.chmod(gradlew_path, 0o755)
            try:
                result = subprocess.run(
                    ['./gradlew', 'assembleDebug'],
                    cwd=workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env={**os.environ, 'ANDROID_HOME': os.environ.get('ANDROID_HOME', '/opt/android-sdk')}
                )
                if result.returncode == 0:
                    apk_path = self._find_apk(workspace_path)
                    if apk_path:
                        self.emit('success', f'APK built successfully: {apk_path}')
                        return {'status': 'success', 'apk_path': apk_path}
                self.emit('message', f'Gradle build output: {result.stdout[-500:]}')
                self.emit('error', f'Build errors: {result.stderr[-500:]}')
            except subprocess.TimeoutExpired:
                self.emit('error', 'APK build timed out (5 min limit)')
            except Exception as e:
                self.emit('error', f'APK build failed: {str(e)}')

        # Return the project files for manual download
        return {
            'status': 'project_ready',
            'message': 'Android project generated. Download the workspace ZIP and build locally with Android Studio or use `./gradlew assembleDebug`.',
            'workspace_path': workspace_path,
        }

    def _find_apk(self, workspace_path: str) -> str:
        for root, dirs, files in os.walk(workspace_path):
            for f in files:
                if f.endswith('.apk'):
                    return os.path.join(root, f)
        return ''

    def _create_gradle_wrapper(self, workspace_path: str):
        """Create a basic gradle wrapper script."""
        wrapper_content = '''#!/bin/bash
# Gradle wrapper - requires Gradle to be installed
if command -v gradle &> /dev/null; then
    gradle "$@"
else
    echo "Gradle not found. Install Gradle or use Android Studio to build."
    exit 1
fi
'''
        gradlew_path = os.path.join(workspace_path, 'gradlew')
        with open(gradlew_path, 'w') as f:
            f.write(wrapper_content)
        os.chmod(gradlew_path, 0o755)

    def _default_android_project(self, description: str) -> dict:
        return {
            'files': [
                {
                    'path': 'app/src/main/java/com/astradev/app/MainActivity.kt',
                    'content': '''package com.astradev.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    MainScreen()
                }
            }
        }
    }
}

@Composable
fun MainScreen() {
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text("AstraDev App", style = MaterialTheme.typography.headlineLarge)
        Spacer(modifier = Modifier.height(16.dp))
        Text("Built with AstraDev AI", style = MaterialTheme.typography.bodyLarge)
    }
}
'''
                },
                {
                    'path': 'app/src/main/AndroidManifest.xml',
                    'content': '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.astradev.app">
    <application
        android:allowBackup="true"
        android:label="AstraDev App"
        android:theme="@style/Theme.Material3.DayNight.NoActionBar">
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
                {
                    'path': 'app/build.gradle.kts',
                    'content': '''plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.astradev.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.astradev.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
}
'''
                },
                {
                    'path': 'build.gradle.kts',
                    'content': '''plugins {
    id("com.android.application") version "8.2.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.22" apply false
}
'''
                },
                {
                    'path': 'settings.gradle.kts',
                    'content': '''pluginManagement {
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
rootProject.name = "AstraDevApp"
include(":app")
'''
                },
                {
                    'path': 'gradle.properties',
                    'content': '''android.useAndroidX=true
kotlin.code.style=official
android.nonTransitiveRClass=true
org.gradle.jvmargs=-Xmx2048m
'''
                },
            ],
            'package_name': 'com.astradev.app',
            'app_name': 'AstraDev App',
            'min_sdk': 24,
            'target_sdk': 34,
        }
