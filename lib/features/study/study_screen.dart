import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../mentor/mentor_screen.dart';
import '../tests/test_runner.dart';

class StudyScreen extends StatelessWidget {
  const StudyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Loader<List<SubjectStat>>(
      load: Api.instance.syllabus,
      builder: (context, subjects, reload) => PageFrame(
        title: 'Study',
        subtitle: 'Learn a topic with the mentor, then take a focused 20-question test.',
        onRefresh: reload,
        children: [
          for (final s in subjects)
            Card(
              clipBehavior: Clip.antiAlias,
              child: ExpansionTile(
                leading: const Icon(Icons.school_outlined),
                title: Text(s.subject),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 4),
                    Text(s.weight > 0
                        ? '${s.topicsStarted}/${s.topicCount} topics started · accuracy ${pct(s.accuracy)}'
                            ' · ~${s.weight} questions in a full mock'
                        : 'Questions from post-specific technical papers'),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(value: s.accuracy ?? 0),
                  ],
                ),
                children: [for (final t in s.topics) _TopicTile(topic: t)],
              ),
            ),
        ],
      ),
    );
  }
}

class _TopicTile extends StatelessWidget {
  const _TopicTile({required this.topic});
  final TopicStat topic;

  @override
  Widget build(BuildContext context) {
    final t = topic;
    return ListTile(
      title: Text(t.topic),
      subtitle: Text(t.attempts == 0
          ? 'Not practised yet · ${t.bankSize} questions in bank'
          : '${pct(t.accuracy)} of last ${t.attempts} · ${t.bankSize} questions in bank'),
      trailing: Wrap(
        spacing: 4,
        children: [
          IconButton(
            tooltip: 'Learn with mentor',
            icon: const Icon(Icons.chat_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => MentorScreen(
                standalone: true,
                initialMessage: 'Teach me "${t.topic}" (${t.subject}) for Kerala PSC: the key facts PSC asks, '
                    'how questions are usually framed, and a memory trick or two.',
              ),
            )),
          ),
          FilledButton.tonal(
            onPressed: () => startTest(context, () => Api.instance.createTest('topic', topicId: t.topicId)),
            child: const Text('Practice'),
          ),
        ],
      ),
    );
  }
}
