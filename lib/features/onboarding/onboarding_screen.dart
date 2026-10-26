import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';

/// After sign-up: the diagnostic mock that shows strong and weak areas.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.user});
  final User user;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  SyncState? _sync;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _refreshSync();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refreshSync() async {
    try {
      final s = await Api.instance.syncStatus();
      if (!mounted) return;
      setState(() => _sync = s);
      _poll?.cancel();
      if (s.running) _poll = Timer(const Duration(seconds: 5), _refreshSync);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final u = widget.user;
    final theme = Theme.of(context);
    final sync = _sync;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Welcome'),
        actions: [
          TextButton(onPressed: () => Api.instance.logout(), child: const Text('Log out')),
        ],
      ),
      body: PageFrame(
        title: 'Hi ${u.name}, let\'s find where you stand',
        subtitle: 'Take one full ${u.examName} mock. It follows the real exam: '
            '${u.examQuestions} questions, ${u.examMinutes} minutes, 1/3 mark cut for each wrong answer. '
            'Questions come from the latest official PSC papers first.',
        children: [
          const Card(
            child: Padding(
              padding: EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Step(Icons.quiz_outlined, 'Answer honestly',
                      'Skip what you don\'t know instead of guessing. Skipped questions cost nothing.'),
                  _Step(Icons.insights_outlined, 'Get your strength report',
                      'Every section is rated Strong, Average or Weak, with the marks you could gain.'),
                  _Step(Icons.schedule, 'Get your time plan',
                      'Your daily study time is shared out so weak, high-mark sections get the most.'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text('Sections in the exam', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          const Wrap(spacing: 8, runSpacing: 8, children: [
            Chip(label: Text('History 10')),
            Chip(label: Text('Geography 5')),
            Chip(label: Text('Economics 5')),
            Chip(label: Text('Civics 5')),
            Chip(label: Text('Constitution 5')),
            Chip(label: Text('Arts, Literature & Sports 10')),
            Chip(label: Text('Computer 5')),
            Chip(label: Text('Science & Tech 5')),
            Chip(label: Text('Arithmetic 10')),
            Chip(label: Text('Mental Ability 10')),
            Chip(label: Text('English 20')),
            Chip(label: Text('Malayalam 10')),
          ]),
          if (sync != null && (sync.running || sync.lastRun != null)) ...[
            const SizedBox(height: 16),
            Card(
              child: ListTile(
                leading: sync.running
                    ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.cloud_done_outlined),
                title: Text(sync.running ? 'Fetching the latest PSC papers…' : 'Question bank up to date'),
                subtitle: Text('${sync.imported} of ${sync.queued} new papers imported'),
              ),
            ),
          ],
          const SizedBox(height: 24),
          FilledButton.icon(
            icon: const Icon(Icons.play_arrow),
            label: const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text('Start diagnostic mock'),
            ),
            onPressed: () => startTest(context, () => Api.instance.createTest('diagnostic')),
          ),
        ],
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step(this.icon, this.title, this.text);
  final IconData icon;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: CircleAvatar(child: Icon(icon)),
      title: Text(title),
      subtitle: Text(text),
    );
  }
}
