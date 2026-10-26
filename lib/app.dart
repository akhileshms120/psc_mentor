import 'package:flutter/material.dart';

import 'core/api.dart';
import 'core/models.dart';
import 'core/ui.dart';
import 'features/auth/auth_screen.dart';
import 'features/dashboard/dashboard_screen.dart';
import 'features/mentor/mentor_screen.dart';
import 'features/onboarding/onboarding_screen.dart';
import 'features/progress/progress_screen.dart';
import 'features/pyq/pyq_screen.dart';
import 'features/study/study_screen.dart';
import 'features/tests/tests_screen.dart';

class PscMentorApp extends StatelessWidget {
  const PscMentorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'PSC Mentor',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF00695C),
        useMaterial3: true,
      ),
      home: const AuthGate(),
    );
  }
}

/// Signed out → account screen; new account → diagnostic mock; otherwise the app.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: Api.instance.signedIn,
      builder: (context, signedIn, _) {
        if (!signedIn) return const AuthScreen();
        return Scaffold(
          body: Loader<User>(
            key: const ValueKey('me'),
            load: Api.instance.me,
            builder: (context, user, _) => user.diagnosticDone ? const AppShell() : OnboardingScreen(user: user),
          ),
        );
      },
    );
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  static const _destinations = <_Destination>[
    _Destination('Home', Icons.home_outlined, Icons.home, DashboardScreen()),
    _Destination('Study', Icons.menu_book_outlined, Icons.menu_book, StudyScreen()),
    _Destination('Tests', Icons.quiz_outlined, Icons.quiz, TestsScreen()),
    _Destination('PYQ', Icons.history_edu_outlined, Icons.history_edu, PyqScreen()),
    _Destination('Mentor', Icons.forum_outlined, Icons.forum, MentorScreen()),
    _Destination('Progress', Icons.insights_outlined, Icons.insights, ProgressScreen()),
  ];

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= 900;
        final body = IndexedStack(
          index: _index,
          children: _destinations.map((item) => item.screen).toList(),
        );

        if (isWide) {
          return Scaffold(
            body: Row(
              children: [
                NavigationRail(
                  selectedIndex: _index,
                  onDestinationSelected: (value) => setState(() => _index = value),
                  labelType: NavigationRailLabelType.all,
                  leading: const Padding(
                    padding: EdgeInsets.symmetric(vertical: 18),
                    child: CircleAvatar(
                      radius: 24,
                      child: Text('PSC'),
                    ),
                  ),
                  destinations: _destinations
                      .map(
                        (item) => NavigationRailDestination(
                          icon: Icon(item.icon),
                          selectedIcon: Icon(item.selectedIcon),
                          label: Text(item.label),
                        ),
                      )
                      .toList(),
                ),
                const VerticalDivider(width: 1),
                Expanded(child: body),
              ],
            ),
          );
        }

        return Scaffold(
          body: body,
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (value) => setState(() => _index = value),
            destinations: _destinations
                .map(
                  (item) => NavigationDestination(
                    icon: Icon(item.icon),
                    selectedIcon: Icon(item.selectedIcon),
                    label: item.label,
                  ),
                )
                .toList(),
          ),
        );
      },
    );
  }
}

class _Destination {
  const _Destination(this.label, this.icon, this.selectedIcon, this.screen);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget screen;
}
