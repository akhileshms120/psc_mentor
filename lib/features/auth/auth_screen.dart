import 'package:flutter/material.dart';

import '../../core/api.dart';
import '../../core/ui.dart';
import '../profile/profile_screen.dart';

/// First screen for a signed-out student: create an account or log in.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _signup = true;
  bool _busy = false;
  String? _error;
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _login = TextEditingController();
  final _password = TextEditingController();
  double _minutes = 120;
  String? _examDate;
  String _language = 'en';

  @override
  void dispose() {
    _name.dispose();
    _login.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_signup) {
        await Api.instance.signup(
          name: _name.text.trim(),
          login: _login.text.trim(),
          password: _password.text,
          dailyMinutes: _minutes.round(),
          examDate: _examDate,
          language: _language,
        );
      } else {
        await Api.instance.login(_login.text.trim(), _password.text);
      }
      // Api.signedIn flips and the app moves on by itself.
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: CircleAvatar(radius: 36, child: Icon(Icons.school, size: 36))),
                    const SizedBox(height: 16),
                    Text('PSC Mentor', textAlign: TextAlign.center, style: theme.textTheme.headlineMedium),
                    const SizedBox(height: 6),
                    Text('Your personal coach for the Kerala PSC Degree Level Preliminary exam',
                        textAlign: TextAlign.center, style: theme.textTheme.bodyLarge),
                    const SizedBox(height: 24),
                    SegmentedButton<bool>(
                      segments: const [
                        ButtonSegment(value: true, label: Text('Create account')),
                        ButtonSegment(value: false, label: Text('Log in')),
                      ],
                      selected: {_signup},
                      onSelectionChanged: (s) => setState(() {
                        _signup = s.first;
                        _error = null;
                      }),
                    ),
                    const SizedBox(height: 20),
                    if (_signup) ...[
                      TextFormField(
                        controller: _name,
                        textCapitalization: TextCapitalization.words,
                        decoration: const InputDecoration(labelText: 'Your name', border: OutlineInputBorder()),
                        validator: (v) => (v ?? '').trim().isEmpty ? 'Enter your name' : null,
                      ),
                      const SizedBox(height: 12),
                    ],
                    TextFormField(
                      controller: _login,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                          labelText: 'Mobile number or email', border: OutlineInputBorder()),
                      validator: (v) => (v ?? '').trim().length < 5 ? 'Enter your mobile number or email' : null,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _password,
                      obscureText: true,
                      decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder()),
                      validator: (v) => _signup && (v ?? '').length < 6 ? 'At least 6 characters' : null,
                      onFieldSubmitted: (_) => _submit(),
                    ),
                    if (_signup) ...[
                      const SizedBox(height: 20),
                      Text('How much time can you study each day? ${_minutes.round()} minutes',
                          style: theme.textTheme.titleSmall),
                      Slider(
                        value: _minutes,
                        min: 30,
                        max: 300,
                        divisions: 18,
                        label: '${_minutes.round()} min',
                        onChanged: (v) => setState(() => _minutes = v),
                      ),
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Exam date (optional)'),
                        subtitle: Text(_examDate ?? 'Not announced yet'),
                        trailing: OutlinedButton(
                          onPressed: () async {
                            final now = DateTime.now();
                            final picked = await showDatePicker(
                              context: context,
                              firstDate: now,
                              lastDate: DateTime(now.year + 3),
                              initialDate: now.add(const Duration(days: 120)),
                            );
                            if (picked != null) {
                              setState(() => _examDate = picked.toIso8601String().substring(0, 10));
                            }
                          },
                          child: const Text('Choose'),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text('Language for questions and the mentor', style: theme.textTheme.titleSmall),
                      const SizedBox(height: 8),
                      SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(value: 'en', label: Text('English')),
                          ButtonSegment(value: 'ml', label: Text('മലയാളം')),
                        ],
                        selected: {_language},
                        onSelectionChanged: (s) => setState(() => _language = s.first),
                      ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      ErrorCard(_error!),
                    ],
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        child: Text(_busy ? 'Please wait…' : (_signup ? 'Create account' : 'Log in')),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextButton.icon(
                      icon: const Icon(Icons.dns_outlined),
                      label: const Text('Server settings'),
                      onPressed: () => Navigator.of(context)
                          .push(MaterialPageRoute<void>(builder: (_) => const ServerSettingsScreen())),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
