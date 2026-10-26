import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';

/// One paper: take it as a timed test, and review every earlier attempt.
class PaperDetailScreen extends StatelessWidget {
  const PaperDetailScreen({super.key, required this.paperId});
  final int paperId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Paper')),
      body: Loader<Paper>(
        load: () => Api.instance.paper(paperId),
        builder: (context, p, reload) {
          final done = p.attempts.where((t) => t.submitted).toList();
          final best = done.isEmpty
              ? null
              : done.map((t) => t.score!).reduce((a, b) => a > b ? a : b);
          return PageFrame(
            title: p.title,
            subtitle: [
              if (p.uploaded) 'Uploaded by you' else 'Official Kerala PSC paper',
              '${p.questionCount} questions',
              if (p.answersLabel.isNotEmpty) p.answersLabel,
              if (p.testDate != null) p.testDate!,
            ].join(' · '),
            onRefresh: reload,
            children: [
              if (p.answerSource == 'ai_solved')
                const Card(
                  child: ListTile(
                    leading: Icon(Icons.info_outline),
                    title: Text('No answer key was uploaded'),
                    subtitle: Text('The AI worked out these answers. They are usually right, but check any '
                        'answer that looks wrong against a trusted key.'),
                  ),
                ),
              if (p.status == 'done')
                FilledButton.icon(
                  icon: const Icon(Icons.play_arrow),
                  label: Text(done.isEmpty ? 'Take this paper as a test' : 'Take it again'),
                  onPressed: () => startTest(context, () => Api.instance.createTest('paper', paperId: p.id)),
                )
              else if (p.busy)
                const ListTile(leading: CircularProgressIndicator(), title: Text('Reading the questions…'))
              else
                ErrorCard('Import failed: ${p.error ?? 'unknown error'}'),
              const SectionTitle('Your attempts'),
              if (done.isEmpty) const Text('No attempts yet.'),
              if (done.length > 1)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text('Best ${best!.toStringAsFixed(2)} · first ${done.last.score!.toStringAsFixed(2)} '
                      '· latest ${done.first.score!.toStringAsFixed(2)}'),
                ),
              for (final t in done)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.fact_check_outlined),
                    title: Text('${t.score!.toStringAsFixed(2)} / ${t.maxScore!.toStringAsFixed(0)}'),
                    subtitle: Text('${t.submittedAt!.substring(0, 10)} · ${t.correct} correct · ${t.wrong} wrong · '
                        '${t.skipped} skipped'),
                    trailing: const Text('Review'),
                    onTap: () => openTest(context, t.id),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
