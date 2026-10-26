# Core data model

## Student
- id
- name
- preferredLanguage
- targetExamId
- dailyStudyMinutes
- examDate

## Exam
- id
- name
- categoryNumber
- syllabusVersion
- markingScheme
- negativeMarkingRule

## Topic
- id
- subjectId
- parentTopicId
- name
- syllabusReference

## Question
- id
- type: verified_pyq | pyq_derived | original_mock
- examId
- subjectId
- topicId
- stem
- options
- correctAnswer
- explanation
- difficulty
- sourcePaperId
- sourceQuestionNumber
- sourceAnswerKeyId
- verificationStatus

## Attempt
- id
- studentId
- questionId
- selectedAnswer
- isCorrect
- responseTimeMs
- confidence
- attemptedAt

## RevisionItem
- id
- studentId
- topicId/questionId
- dueAt
- intervalStage
- lastResult

## Test
- id
- studentId
- type: topic | daily | weekly | monthly | mistake_bank
- examPatternVersion
- startedAt
- submittedAt
- score
- accuracy
