vi.mock('leaflet', () => ({
    default: {
        icon: vi.fn().mockReturnValue({}),
        map: vi.fn().mockReturnValue({}),
        circleMarker: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
        polyline: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
        divIcon: vi.fn().mockReturnValue({ options: {} }),
        point: vi.fn((x: number, y: number) => ({ x, y })),
    },
    icon: vi.fn().mockReturnValue({}),
    map: vi.fn().mockReturnValue({}),
    circleMarker: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
    polyline: vi.fn().mockReturnValue({ bindPopup: vi.fn().mockReturnThis(), addTo: vi.fn().mockReturnThis(), setStyle: vi.fn().mockReturnThis() }),
    divIcon: vi.fn().mockReturnValue({ options: {} }),
    point: vi.fn((x: number, y: number) => ({ x, y })),
}));

import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { GameService, Quiz } from './game-service';

const QUIZ_ENDPOINT = '/api/jeux-informatifs/quiz';

const MOCK_QUIZ: Quiz = {
    answeredQuestionList: [1],
    questions: [
        {
            question: {
                questionText: 'What is renewable energy?',
                options: ['Solar', 'Coal', 'Gas', 'Oil'],
                questionType: 'single',
                questionAspect: 'energy',
            },
            answer: 0,
            message: 'Solar is renewable!',
        },
        {
            question: {
                questionText: 'Which is green?',
                options: ['Nuclear', 'Wind', 'Diesel', 'Petrol'],
                questionType: 'single',
                questionAspect: 'environment',
            },
            answer: 1,
            message: 'Wind is green!',
        },
        {
            question: {
                questionText: 'Best for economy?',
                options: ['Hydro', 'Gas', 'Coal', 'Nuclear'],
                questionType: 'single',
                questionAspect: 'economy',
            },
            answer: 0,
            message: 'Hydro is cheap!',
        },
    ] as any,
};

const MOCK_ORDER_QUIZ: Quiz = {
    answeredQuestionList: [2],
    questions: [
        {
            question: {
                questionText: 'Order these by cost:',
                options: ['A', 'B', 'C'],
                questionType: 'order',
                questionAspect: 'economy',
            },
            answer: [0, 1, 2],
            message: 'A, B, C is the correct order.',
        },
    ] as any,
};

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('GameService', () => {
    let service: GameService;
    let httpMock: HttpTestingController;

    const flushInitialQuiz = (quiz = MOCK_QUIZ) => {
        const req = httpMock.expectOne((r) => r.url === QUIZ_ENDPOINT);
        req.flush(quiz);
    };

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [GameService, provideHttpClient(), provideHttpClientTesting()],
        });

        service = TestBed.inject(GameService);
        httpMock = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
        httpMock.verify();
        vi.clearAllMocks();
    });

    describe('initialization', () => {
        it('should call the quiz endpoint on construction', () => {
            httpMock.expectOne((r) => r.url === QUIZ_ENDPOINT);
        });

        it('should start with quizStarted = false', () => {
            flushInitialQuiz();
            expect(service.isQuizStarted()).toBe(false);
        });
    });

    describe('after quiz loads', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('getQuestion should return the first question', () => {
            const q = service.getQuestion();
            expect(q.questionText).toBe('What is renewable energy?');
        });

        it('getMessage should return the message for the current question', () => {
            expect(service.getMessage()).toBe('Solar is renewable!');
        });

        it('totalQuestions should equal the number of quiz questions', () => {
            expect(service.totalQuestions).toBe(3);
        });

        it('questionIndex should start at 0', () => {
            expect(service.questionIndex).toBe(0);
        });

        it('getQuestionAspect should return array of aspects', () => {
            const aspects = service.getQuestionAspect();
            expect(aspects).toEqual(['energy', 'environment', 'economy']);
        });
    });

    describe('nextQuestion', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('should advance to the next question', () => {
            service.nextQuestion();
            expect(service.questionIndex).toBe(1);
        });

        it('should reset isCurrentAnswered on nextQuestion', () => {
            service.checkAnswer([0]);
            expect(service.isCurrentAnswered).toBe(true);
            service.nextQuestion();
            expect(service.isCurrentAnswered).toBe(false);
        });

        it('should emit NO_MORE_QUESTIONS_FLAG after the last question', () => {
            service.nextQuestion(); // q1 → q2
            service.nextQuestion(); // q2 → q3 (last)
            service.nextQuestion(); // q3 → flag (-2)
            expect(service.questionIndex).toBe(-2);
        });
    });

    describe('checkAnswer - single answer', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('should mark energy aspect as correct when answer is right', () => {
            service.checkAnswer([0]); // correct is 0, aspect is 'energy'
            expect(service.getEnergyNumber()).toBe(1);
            expect(service.getGoodAnswerNumber()).toBe(1);
        });

        it('should not add to score when answer is wrong', () => {
            service.checkAnswer([1]); // wrong
            expect(service.getEnergyNumber()).toBe(0);
            expect(service.getGoodAnswerNumber()).toBe(0);
        });

        it('should return the correct answer index', () => {
            const result = service.checkAnswer([0]);
            expect(result).toEqual([0]);
        });

        it('should not double-count when answering the same question twice', () => {
            service.checkAnswer([0]);
            service.checkAnswer([0]);
            expect(service.getEnergyNumber()).toBe(1);
        });

        it('should count environment aspect correctly', () => {
            service.nextQuestion(); // q2: environment
            service.checkAnswer([1]); // correct
            expect(service.getEnvironmentNumber()).toBe(1);
        });

        it('should count economy aspect correctly', () => {
            service.nextQuestion();
            service.nextQuestion(); // q3: economy
            service.checkAnswer([0]); // correct
            expect(service.getEconomyNumber()).toBe(1);
        });
    });

    describe('checkAnswer - order answer (array)', () => {
        beforeEach(() => {
            flushInitialQuiz(MOCK_ORDER_QUIZ);
        });

        it('should return the correct answer array', () => {
            const result = service.checkAnswer([0, 1, 2]);
            expect(result).toEqual([0, 1, 2]);
        });

        it('should give full points for a fully correct order answer', () => {
            service.checkAnswer([0, 1, 2]); // fully correct
            expect(service.getEconomyNumber()).toBe(1);
        });

        it('should give partial points for partially correct order', () => {
            service.checkAnswer([0, 2, 1]); // 2 of 3 correct
            expect(service.getEconomyNumber()).toBeGreaterThan(0);
            expect(service.getEconomyNumber()).toBeLessThan(1);
        });

        it('should give no points when length differs', () => {
            service.checkAnswer([0, 1]); // wrong length
            expect(service.getEconomyNumber()).toBe(0);
        });

        it('should return empty array when answer is unknown type', () => {
            (service as any).quiz.questions[0].answer = undefined;
            const result = service.checkAnswer([0]);
            expect(result).toEqual([]);
        });
    });

    describe('restartAvailable / restartQuestions', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('restartAvailable should return true initially', () => {
            expect(service.restartAvailable()).toBe(true);
        });

        it('restartAvailable should return false when NO_MORE_QUESTIONS_FLAG is set', () => {
            (service as any).answeredQuestions = [-2];
            expect(service.restartAvailable()).toBe(false);
        });

        it('restartQuestions should reset answered questions', () => {
            (service as any).answeredQuestions = [1, 2, 3];
            service.restartQuestions();
            expect((service as any).answeredQuestions).toEqual([-1]);
        });
    });

    describe('setQuizStarted / isQuizStarted', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('should return true after setQuizStarted is called', () => {
            service.setQuizStarted();
            expect(service.isQuizStarted()).toBe(true);
        });
    });

    describe('getAnsweredQuestions', () => {
        beforeEach(() => {
            flushInitialQuiz();
        });

        it('should return empty arrays when no questions answered', () => {
            const result = service.getAnsweredQuestions();
            expect(result.questions).toHaveLength(0);
            expect(result.answers).toHaveLength(0);
            expect(result.correctAnswers).toHaveLength(0);
        });

        it('should return answered question data after answering', () => {
            service.checkAnswer([0]); // answer q1
            const result = service.getAnsweredQuestions();
            expect(result.questions).toHaveLength(1);
            expect(result.questions[0]).toBe('What is renewable energy?');
            expect(result.color[0]).toBe('green');
        });

        it('should return red color for a wrong answer', () => {
            service.checkAnswer([2]); // wrong
            const result = service.getAnsweredQuestions();
            expect(result.color[0]).toBe('red');
        });

        it('should return correct answer text', () => {
            service.checkAnswer([2]); // wrong answer
            const result = service.getAnsweredQuestions();
            expect(result.correctAnswers[0]).toBe('Solar'); // options[0]
        });
    });

    describe('getQuiz refresh', () => {
        it('should fetch again when getQuiz is called after construction', async () => {
            flushInitialQuiz();
            await tick();

            service.getQuiz();
            httpMock.expectOne((r) => r.url === QUIZ_ENDPOINT).flush(MOCK_QUIZ);
        });
    });
});
