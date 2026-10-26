import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import 'test_runner.dart';

class TestsScreen extends StatelessWidget {
  const TestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Loader<List<TestInfo>>(
      load: Api.instance.tests,
      builder: (context, tests, reload) => PageFrame(
        title: 'Mock Tests',
        subtitle: 'PSC pattern: 1 mark per question, 1/3 mark cut for each wrong answer.',
        onRefresh: reload,
        children: [
          const _TestCard(
            type: 'daily',
            title: 'Daily Practice',
            description: '15 questions from today\'s plan, revision and weak areas.',
            icon: Icons.today_outlined,
          ),
          const _TestCard(
            type: 'weekly',
            title: 'Weekly Test',
            description: '50 questions on this week\'s topics plus your weak areas · 45 min.',
            icon: Icons.calendar_view_week_outlined,
          ),
          const _TestCard(
            type: 'monthly',
            title: 'Monthly Full Mock',
            description: '100 questions across the syllabus in exam proportions · 75 min.',
            icon: Icons.fact_check_outlined,
          ),
          const _TestCard(
            type: 'mistakes',
            title: 'Mistake Bank',
            description: 'Retest questions you answered wrongly, on a spaced-revision schedule.',
            icon: Icons.replay_circle_filled_outlined,
          ),
          const Card(
            child: ListTile(
              leading: Icon(Icons.topic_outlined),
              title: Text('Topic Test'),
              subtitle: Text('Start a 20-question test on any topic from the Study tab.'),
            ),
          ),
          const SectionTitle('History'),
          if (tests.isEmpty) const Text('No tests yet. Start with today\'s daily practice.'),
          for (final t in tests)
            Card(
              child: ListTile(
                leading: Icon(t.submitted ? Icons.check_circle_outline : Icons.pending_outlined),
                title: Text(t.title),
                subtitle: Text('${t.createdAt.substring(0, 10)} · ${t.questionCount} questions'),
                trailing: Text(
                  t.submitted ? '${t.score!.toStringAsFixed(1)} / ${t.maxScore!.toStringAsFixed(0)}' : 'Resume',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                onTap: () => openTest(context, t.id),
              ),
            ),
        ],
      ),
    );
  }
}

class _TestCard extends StatelessWidget {
  const _TestCard({required this.type, required this.title, required this.description, required this.icon});

  final String type;
  final String title;
  final String description;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            CircleAvatar(child: Icon(icon)),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 5),
                  Text(description),
                ],
              ),
            ),
            const SizedBox(width: 10),
            FilledButton(
              onPressed: () => startTest(context, () => Api.instance.createTest(type)),
              child: const Text('Start'),
            ),
          ],
        ),
      ),
    );
  }
}
