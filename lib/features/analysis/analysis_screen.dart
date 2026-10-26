import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';

Color statusColor(BuildContext context, String status) => switch (status) {
      'strong' => Colors.green.shade700,
      'average' => Colors.orange.shade800,
      'weak' => Theme.of(context).colorScheme.error,
      _ => Theme.of(context).colorScheme.outline,
    };

String hoursMinutes(int minutes) {
  final h = minutes ~/ 60, m = minutes % 60;
  if (h == 0) return '$m min';
  return m == 0 ? '$h h' : '$h h $m min';
}

/// Strong and weak areas, marks at stake, and the weekly time each section gets.
class AnalysisScreen extends StatelessWidget {
  const AnalysisScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Strength report')),
      body: Loader<StrengthReport>(
        load: Api.instance.analysis,
        builder: (context, r, reload) => PageFrame(
          title: r.estimatedScore == null
              ? 'Take the diagnostic mock first'
              : 'Estimated score: ${r.estimatedScore!.toStringAsFixed(1)} / ${r.maxScore}',
          subtitle: r.assessed
              ? 'From your diagnostic mock and every test since, with negative marking applied. '
                  'Your ${hoursMinutes(r.weeklyStudyMinutes)} of weekly study time is shared out below: '
                  'weak sections that carry more marks get more time, and strong sections get some '
                  'practice so they stay strong.'
              : 'The diagnostic mock shows which sections are strong and which need work.',
          onRefresh: reload,
          children: [
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final s in ['weak', 'average', 'strong'])
                Chip(
                  avatar: CircleAvatar(backgroundColor: statusColor(context, s), radius: 6),
                  label: Text('${switch (s) {
                    'weak' => 'Weak (below 50%)',
                    'average' => 'Average (50–69%)',
                    _ => 'Strong (70% +)',
                  }}: ${r.sections.where((x) => x.status == s).length}'),
                ),
            ]),
            const SizedBox(height: 12),
            for (final s in r.sections) SectionCard(section: s),
          ],
        ),
      ),
    );
  }
}

class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.section});
  final SectionReport section;

  @override
  Widget build(BuildContext context) {
    final s = section;
    final color = statusColor(context, s.status);
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(child: Text(s.subject, style: theme.textTheme.titleMedium)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                child: Text(s.statusLabel, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
              ),
            ]),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: s.accuracy ?? 0, color: color, minHeight: 8),
            const SizedBox(height: 8),
            Text('${pct(s.accuracy)} accuracy · ${s.marks} marks in the exam'
                '${s.expectedMarks == null ? '' : ' · you would score about ${s.expectedMarks!.toStringAsFixed(1)}'}'),
            const SizedBox(height: 4),
            Text('Study ${hoursMinutes(s.weeklyMinutes)} a week'
                '${(s.potentialGain ?? 0) > 0 ? ' · up to ${s.potentialGain!.toStringAsFixed(1)} marks to gain' : ''}',
                style: theme.textTheme.titleSmall),
            if (s.weakTopics.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('Work on:', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final t in s.weakTopics)
                  ActionChip(
                    avatar: const Icon(Icons.play_arrow, size: 18),
                    label: Text('${t.topic} · ${pct(t.accuracy)}'),
                    onPressed: () => startTest(context, () => Api.instance.createTest('topic', topicId: t.topicId)),
                  ),
              ]),
            ],
            if (s.strongTopics.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Strong: ${s.strongTopics.map((t) => t.topic).join(', ')}', style: theme.textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}
