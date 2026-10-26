import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/models.dart';
import '../../core/ui.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Profile & settings')),
      body: Loader<User>(
        load: Api.instance.me,
        builder: (context, user, reload) => _ProfileForm(user: user),
      ),
    );
  }
}

class _ProfileForm extends StatefulWidget {
  const _ProfileForm({required this.user});
  final User user;

  @override
  State<_ProfileForm> createState() => _ProfileFormState();
}

class _ProfileFormState extends State<_ProfileForm> {
  late final _name = TextEditingController(text: widget.user.name);
  late double _minutes = widget.user.dailyMinutes.toDouble();
  late String? _examDate = widget.user.examDate;
  late String _language = widget.user.language;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    try {
      await Api.instance.updateMe({
        'name': _name.text.trim().isEmpty ? widget.user.name : _name.text.trim(),
        'daily_minutes': _minutes.round(),
        'exam_date': _examDate,
        'language': _language,
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved. Your plan was updated.')));
      }
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  Future<void> _deleteAccount() async {
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete your account?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('This permanently removes your tests, progress, study plan, mentor chat and '
                'uploaded papers. It cannot be undone.'),
            const SizedBox(height: 12),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Password'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final navigator = Navigator.of(context);
    try {
      await Api.instance.deleteAccount(password.text);
      navigator.popUntil((r) => r.isFirst);
    } catch (e) {
      if (mounted) showError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final u = widget.user;
    return PageFrame(
      title: u.examName,
      subtitle: '${u.examQuestions} questions · ${u.examMinutes} minutes · logged in as ${u.login}',
      children: [
        TextField(controller: _name, decoration: const InputDecoration(labelText: 'Your name')),
        const SizedBox(height: 16),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Exam date'),
          subtitle: Text(_examDate ?? 'Not set'),
          trailing: OutlinedButton(
            onPressed: () async {
              final now = DateTime.now();
              final picked = await showDatePicker(
                context: context,
                firstDate: now,
                lastDate: DateTime(now.year + 3),
                initialDate: DateTime.tryParse(_examDate ?? '') ?? now.add(const Duration(days: 90)),
              );
              if (picked != null) setState(() => _examDate = picked.toIso8601String().substring(0, 10));
            },
            child: const Text('Choose'),
          ),
        ),
        Text('Daily study time: ${_minutes.round()} minutes'),
        Slider(value: _minutes, min: 30, max: 300, divisions: 18, onChanged: (v) => setState(() => _minutes = v)),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'en', label: Text('English')),
            ButtonSegment(value: 'ml', label: Text('മലയാളം')),
          ],
          selected: {_language},
          onSelectionChanged: (s) => setState(() => _language = s.first),
        ),
        const SizedBox(height: 20),
        FilledButton(onPressed: _save, child: const Text('Save')),
        const SectionTitle('Account'),
        Wrap(spacing: 12, runSpacing: 12, children: [
          OutlinedButton.icon(
            icon: const Icon(Icons.dns_outlined),
            label: const Text('Server settings'),
            onPressed: () => Navigator.of(context)
                .push(MaterialPageRoute<void>(builder: (_) => const ServerSettingsScreen())),
          ),
          TextButton.icon(
            icon: const Icon(Icons.delete_forever_outlined),
            label: const Text('Delete account'),
            style: TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
            onPressed: _deleteAccount,
          ),
          OutlinedButton.icon(
            icon: const Icon(Icons.logout),
            label: const Text('Log out'),
            onPressed: () async {
              final navigator = Navigator.of(context);
              await Api.instance.logout();
              navigator.popUntil((r) => r.isFirst);
            },
          ),
        ]),
      ],
    );
  }
}

class ServerSettingsScreen extends StatefulWidget {
  const ServerSettingsScreen({super.key});

  @override
  State<ServerSettingsScreen> createState() => _ServerSettingsScreenState();
}

class _ServerSettingsScreenState extends State<ServerSettingsScreen> {
  final _server = TextEditingController(text: Api.instance.baseUrl);
  String? _status;

  @override
  void dispose() {
    _server.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    await Api.instance.setBaseUrl(_server.text);
    try {
      final ai = await Api.instance.health();
      setState(() => _status = ai ? 'Connected · AI mentor on' : 'Connected · AI mentor off (no Gemini API key on server)');
    } catch (e) {
      setState(() => _status = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Server')),
      body: PageFrame(
        title: 'Server address',
        subtitle: 'Where the PSC Mentor server is running.',
        children: [
          TextField(
            controller: _server,
            decoration: const InputDecoration(
              labelText: 'PSC Mentor server address',
              helperText: 'Hosted: ${Api.hostedUrl} · server on this computer: http://localhost:8000',
            ),
          ),
          const SizedBox(height: 12),
          Wrap(spacing: 12, runSpacing: 8, children: [
            OutlinedButton(onPressed: _test, child: const Text('Save & test connection')),
            TextButton(
              onPressed: () {
                _server.text = Api.hostedUrl;
                _test();
              },
              child: const Text('Use hosted server'),
            ),
          ]),
          if (_status != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_status!)),
        ],
      ),
    );
  }
}
