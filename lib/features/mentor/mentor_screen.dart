import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';
import '../tests/test_runner.dart';

/// Chat with the AI mentor. As a tab it shows the running conversation; pushed with
/// [initialMessage] (e.g. "explain this question") it sends that message straight away.
class MentorScreen extends StatefulWidget {
  const MentorScreen({super.key, this.standalone = false, this.initialMessage});

  final bool standalone;
  final String? initialMessage;

  @override
  State<MentorScreen> createState() => _MentorScreenState();
}

class _MentorScreenState extends State<MentorScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _messages = [];
  final Map<int, TestInfo> _tests = {};
  bool _loading = true;
  bool _sending = false;
  Object? _error;

  static const _suggestions = [
    'What should I study today?',
    'Give me a test on my weakest topic',
    'How am I doing this week?',
    'എന്റെ ദുർബല വിഷയങ്ങൾ ഏതൊക്കെ?',
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final history = await Api.instance.chatHistory();
      if (!mounted) return;
      setState(() {
        _messages
          ..clear()
          ..addAll(history);
        _loading = false;
        _error = null;
      });
      _toBottom();
      if (widget.initialMessage != null && _messages.every((m) => m.content != widget.initialMessage)) {
        _send(widget.initialMessage!);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = e;
        });
      }
    }
  }

  void _toBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _send(String text) async {
    text = text.trim();
    if (text.isEmpty || _sending) return;
    _input.clear();
    setState(() {
      _messages.add(ChatMessage(role: 'user', content: text));
      _sending = true;
    });
    _toBottom();
    try {
      final reply = await Api.instance.chat(text);
      if (!mounted) return;
      setState(() {
        final testId = reply.tests.isEmpty ? null : reply.tests.last.id;
        for (final t in reply.tests) {
          _tests[t.id] = t;
        }
        _messages.add(ChatMessage(role: 'assistant', content: reply.reply, testId: testId));
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _messages.removeLast());
      _input.text = text;
      showError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
      _toBottom();
    }
  }

  @override
  Widget build(BuildContext context) {
    final body = _loading
        ? const Center(child: CircularProgressIndicator())
        : _error != null
            ? Center(child: Padding(padding: const EdgeInsets.all(24), child: ErrorCard(_error!, onRetry: _load)))
            : Column(
                children: [
                  Expanded(
                    child: _messages.isEmpty
                        ? _Welcome(onPick: _send)
                        : ListView.builder(
                            controller: _scroll,
                            padding: const EdgeInsets.all(16),
                            itemCount: _messages.length + (_sending ? 1 : 0),
                            itemBuilder: (context, i) {
                              if (i == _messages.length) return const _Typing();
                              final m = _messages[i];
                              return _Bubble(message: m, test: m.testId == null ? null : _tests[m.testId]);
                            },
                          ),
                  ),
                  _Composer(controller: _input, sending: _sending, onSend: () => _send(_input.text)),
                ],
              );
    if (widget.standalone) {
      return Scaffold(appBar: AppBar(title: const Text('PSC Mentor')), body: SafeArea(child: body));
    }
    return SafeArea(child: body);
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.onPick});
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            children: [
              const CircleAvatar(radius: 32, child: Icon(Icons.school, size: 32)),
              const SizedBox(height: 16),
              Text('Your PSC mentor', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text(
                'Ask about any topic, get answers explained, or ask for a test. '
                'The mentor sees your scores and weak areas. English or Malayalam.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: [
                  for (final s in _MentorScreenState._suggestions)
                    ActionChip(label: Text(s), onPressed: () => onPick(s)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.message, this.test});
  final ChatMessage message;
  final TestInfo? test;

  @override
  Widget build(BuildContext context) {
    final mine = message.role == 'user';
    final scheme = Theme.of(context).colorScheme;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 6),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: mine ? scheme.primaryContainer : scheme.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(message.content),
              if (message.testId != null) ...[
                const SizedBox(height: 10),
                FilledButton.icon(
                  icon: const Icon(Icons.play_arrow),
                  label: Text(test == null ? 'Open test' : 'Start: ${test!.title} (${test!.questionCount} Q)'),
                  onPressed: () => openTest(context, message.testId!),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Typing extends StatelessWidget {
  const _Typing();

  @override
  Widget build(BuildContext context) {
    return const Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: EdgeInsets.all(12),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          SizedBox(width: 10),
          Text('Mentor is thinking…'),
        ]),
      ),
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({required this.controller, required this.sending, required this.onSend});

  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              minLines: 1,
              maxLines: 5,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              decoration: const InputDecoration(
                hintText: 'Ask your mentor…',
                border: OutlineInputBorder(),
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(onPressed: sending ? null : onSend, icon: const Icon(Icons.send)),
        ],
      ),
    );
  }
}
