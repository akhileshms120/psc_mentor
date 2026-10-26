import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../analysis/analysis_screen.dart';
import '../tests/test_runner.dart';

class ProgressScreen extends StatelessWidget {
  const ProgressScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Loader<(ProgressSummary, List<TestInfo>)>(
      load: () async => (await Api.instance.summary(), await Api.instance.tests()),
      builder: (context, data, reload) {
        final (s, tests) = data;
        final general = s.subjects.where((x) => x.weight > 0).toList();
        final done = tests.where((t) => t.submitted).take(10).toList();
        return PageFrame(
          title: 'Progress',
          subtitle: 'Accuracy by subject, weak areas, and how your scores are moving.',
          onRefresh: reload,
          children: [
            CardGrid(children: [
              InfoCard(title: 'Overall accuracy', value: pct(s.accuracy), icon: Icons.track_changes,
                  caption: '${s.attempts} questions answered'),
              InfoCard(title: 'Last 7 days', value: pct(s.weekAccuracy), icon: Icons.date_range,
                  caption: '${s.weekAttempts} questions'),
              InfoCard(title: 'Syllabus covered', value: pct(s.coverage), icon: Icons.map_outlined,
                  caption: '${s.testsTaken} tests taken · ${s.streakDays}-day streak'),
            ]),
            const SizedBox(height: 12),
            FilledButton.tonalIcon(
              icon: const Icon(Icons.insights),
              label: const Text('Strength report & weekly time plan'),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const AnalysisScreen())),
            ),
            const SectionTitle('Subjects'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    for (final sub in general)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Row(
                          children: [
                            SizedBox(width: 170, child: Text(sub.subject)),
                            Expanded(child: LinearProgressIndicator(value: sub.accuracy ?? 0, minHeight: 8)),
                            SizedBox(
                              width: 110,
                              child: Text('  ${pct(sub.accuracy)} · ${sub.attempts} Q', textAlign: TextAlign.right),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SectionTitle('Weak areas'),
            if (s.weakTopics.isEmpty)
              const Text('No weak topics yet. A topic is flagged after 5+ attempts below 60% accuracy.'),
            for (final t in s.weakTopics)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.warning_amber_outlined),
                  title: Text(t.topic),
                  subtitle: Text('${t.subject} · ${pct(t.accuracy)} of last ${t.attempts}'),
                  trailing: FilledButton.tonal(
                    onPressed: () => startTest(context, () => Api.instance.createTest('topic', topicId: t.topicId)),
                    child: const Text('Practice'),
                  ),
                ),
              ),
            const SectionTitle('Revision'),
            Card(
              child: ListTile(
                leading: const Icon(Icons.replay),
                title: Text('${s.revisionDue} questions due for revision'),
                subtitle: const Text('Wrong answers come back after 1 → 3 → 7 → 15 → 30 days until you get them right.'),
                trailing: s.revisionDue == 0
                    ? null
                    : FilledButton.tonal(
                        onPressed: () => startTest(context, () => Api.instance.createTest('mistakes')),
                        child: const Text('Revise'),
                      ),
              ),
            ),
            const SectionTitle('Recent scores'),
            if (done.isEmpty) const Text('Take a test to see your scores here.'),
            for (final t in done)
              Card(
                child: ListTile(
                  title: Text(t.title),
                  subtitle: Text(t.submittedAt!.substring(0, 10)),
                  trailing: Text('${(t.score! / t.maxScore! * 100).round()}%',
                      style: Theme.of(context).textTheme.titleMedium),
                  onTap: () => openTest(context, t.id),
                ),
              ),
          ],
        );
      },
    );
  }
}
