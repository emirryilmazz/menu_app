import json
from flask import Flask, jsonify, request, make_response
from flask_restful import Resource, Api, reqparse
from functools import wraps
import os
import psycopg2
import psycopg2.extras
from datetime import date, datetime
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager, verify_jwt_in_request, \
    get_jwt

app = Flask(__name__)
api = Api(app)

app.config["JWT_SECRET_KEY"] = "super-secret"  # Change this!
jwt = JWTManager(app)

conn = None


def get_db_connection():
    global conn
    if conn is None:
        conn = psycopg2.connect("host=%s user=%s password=%s dbname=%s" % (os.environ['POSTGRES_HOST'],
                            os.environ['POSTGRES_USERNAME'],
                            os.environ['POSTGRES_PASSWORD'],
                            os.environ['POSTGRES_DB']))
        #conn = psycopg2.connect("host=%s user=%s password=%s dbname=%s" % ('localhost',
        #                                                                   'postgres',
        #                                                                   'a',
        #                                                                   'menu_app'))
        conn.autocommit = True
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return cursor


def query_creator(method, table, columns='', values=tuple(), where='id', id=None):
    if method == 'select':
        query = "SELECT * FROM %s" % table
    elif method == 'select_where':
        query = "SELECT * FROM %s WHERE %s = %s" % (table, where, id)
    elif method == 'insert':
        query = "INSERT INTO %s (%s) VALUES %s" % (table, columns, values)
        query += " RETURNING *"
    elif method == 'update':
        update_string = ''
        for idx, col in enumerate(columns.split(', ')):
            val = values[idx]
            if type(val) == str:
                val = "'" + val + "'"
            update_string += col + " = " + val
            if idx != len(columns.split(', ')) - 1:
                update_string = update_string + ', '
        query = "UPDATE %s SET %s WHERE %s = %s" % (table, update_string, where, id)
        print(query)
    elif method == 'delete':
        query = "DELETE FROM %s WHERE %s = %s" % (table, where, id)
    else:
        return None
    return query


def columns_values_creator(columns, extra_values=None, extra_columns=None):
    values = []
    for col in columns:
        print(col, request.form[col])
        if request.form[col]:
            values.append(request.form[col])
    if extra_values is not None:
        columns.extend(extra_columns)
        values.extend(extra_values)
    columns = ', '.join(columns)
    values = tuple(values)
    return columns, values


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            print(claims)
            if claims["is_administrator"]:
                return fn(*args, **kwargs)
            else:
                return {'msg': 'Admins only!'}, 403

        return decorator

    return wrapper


def user_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims and claims["is_user"]:
                return fn(*args, **kwargs)
            else:
                return jsonify(msg="Users only!"), 403

        return decorator

    return wrapper


def restaurant_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims["is_restaurant"]:
                return fn(*args, **kwargs)
            else:
                return jsonify(msg="Admins only!"), 403

        return decorator

    return wrapper


def jwt_control(jwt_token):
    try:
        jwt = jwt_token.split(' ')[1]
        phone = get_jwt_identity()
        query = "SELECT * FROM users WHERE mobile_phone_number = '%s'" % phone
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        if rows is None:
            return False
        return True
    except:
        return False


class UserRegister(Resource):
    def post(self):
        columns = ['name', 'surname', 'password', 'mobile_phone_number', 'gender']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'users', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        user = cur.fetchone()
        id = user['id']
        access_token = create_access_token(id, additional_claims={"is_user": True, "is_restaurant": False,
                                                                  "is_administrator": False})
        return {'Status': 201, 'access_token': access_token}


class AdminRegister(Resource):
    def post(self):
        columns = ['name', 'surname', 'password', 'mobile_phone_number', 'gender']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'admins', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        user = cur.fetchone()
        id = user['id']
        access_token = create_access_token(id, additional_claims={"is_user": False, "is_restaurant": False,
                                                                  "is_administrator": True})
        return {'Status': 201, 'access_token': access_token}


class RestaurantRegister(Resource):
    def post(self):
        columns = ['name', 'legal_name', 'photo', 'description', 'address', 'menu_description']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'restaurants', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        restaurant = cur.fetchone()
        id = restaurant['id']
        print(id)
        print(request.form['password'], request.form['mobile_phone_number'])
        query = "INSERT INTO restaurant_credentials (restaurant_id, password, mobile_phone_number) VALUES (%s, '%s', '%s')" % (
        id, request.form['password'], request.form['mobile_phone_number'])
        cur.execute(query)
        access_token = create_access_token(id, additional_claims={"is_user": False, "is_restaurant": True,
                                                                  "is_administrator": False})
        return {'Status': 201, 'access_token': access_token}


class UserLogin(Resource):
    def post(self):
        phone = request.form['mobile_phone_number']
        password = request.form['password']
        print(phone, password)
        query = "SELECT * FROM users WHERE mobile_phone_number = '%s' AND password = '%s'" % (phone, password)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        if rows is None:
            return {'Status': 401, 'message': 'Invalid username or password'}
        id = rows['id']
        access_token = create_access_token(id, additional_claims={"is_user": True, "is_restaurant": False,
                                                                  "is_administrator": False})
        return {'Status': 200, 'access_token': access_token}


class AdminLogin(Resource):
    def post(self):
        phone = request.form['mobile_phone_number']
        password = request.form['password']
        print(phone, password)
        query = "SELECT * FROM admins WHERE mobile_phone_number = '%s' AND password = '%s'" % (phone, password)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        if rows is None:
            return {'Status': 401, 'message': 'Invalid phone or password'}
        id = rows['id']
        access_token = create_access_token(id, additional_claims={"is_user": False, "is_restaurant": False,
                                                                  "is_administrator": True})
        return {'Status': 200, 'access_token': access_token}


class RestaurantLogin(Resource):
    def post(self):
        phone = request.form['mobile_phone_number']
        password = request.form['password']
        print(phone, password)
        query = "SELECT * FROM restaurant_credentials WHERE mobile_phone_number = '%s' AND password = '%s'" % (
        phone, password)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        if rows is None:
            return {'Status': 401, 'message': 'Invalid phone or password'}
        id = rows['restaurant_id']
        access_token = create_access_token(id, additional_claims={"is_user": False, "is_restaurant": True,
                                                                  "is_administrator": False})
        return {'Status': 200, 'access_token': access_token}


class Users(Resource):

    @admin_required()
    def get(self):
        current_user = get_jwt_identity()
        print(current_user)
        query = query_creator('select', 'users')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)

    @admin_required()
    def post(self):
        columns = ['name', 'surname', 'password', 'mobile_phone_number', 'gender']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'users', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class User(Resource):
    def get(self, user_id):
        query = query_creator('select_where', 'users', id=user_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @admin_required()
    def put(self, user_id):
        columns = ['name', 'surname', 'password', 'mobile_phone_number', 'gender']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('update', 'users', col_strings, values, id=user_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}

    @admin_required()
    def delete(self, user_id):
        query = query_creator('delete', 'users', id=user_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class MyReviews(Resource):
    @user_required()
    def get(self):
        current_user = get_jwt_identity()
        userReviews = UserReviews()
        return userReviews.get(current_user)


class UserReviews(Resource):
    @admin_required()
    def get(self, user_id):
        query = "SELECT * FROM reservations RIGHT JOIN reviews ON reviews.reservation_id = reservations.id WHERE reservations.user_id = %s" % user_id
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        return jsonify(rows)


class MyReservations(Resource):
    @user_required()
    def get(self):
        current_user = get_jwt_identity()
        print('crr', current_user)
        userReservations = UserReservations()
        return userReservations.get(current_user)

    @user_required()
    def post(self):
        current_user = get_jwt_identity()
        columns = ['waiter_id', 'restaurant_id', 'status', 'reservation_date', 'reservation_hour', 'persons',
                   'reservation_status']
        reservation_hour = request.form['reservation_hour']
        reservation_date = request.form['reservation_date']
        restaurant_id = request.form['restaurant_id']
        if if_reservation_available(self, reservation_date, reservation_hour, restaurant_id):
            col_strings, values = columns_values_creator(columns, extra_values=[current_user],
                                                         extra_columns=['user_id'])
            query = query_creator('insert', 'reservations', col_strings, values)
            cur = get_db_connection()
            cur.execute(query)
            return {'Status': 201}
        else:
            return {'Status': 400, 'message': 'Reservation is not available'}


class MyReservation(Resource):
    @user_required()
    def get(self, reservation_id):
        query = query_creator('select_where', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        rows['reservation_date'] = rows['reservation_date'].strftime("%Y-%m-%d")
        rows['reservation_hour'] = rows['reservation_hour'].strftime("%H:%M")
        return jsonify(rows)

    @user_required()
    def put(self, reservation_id):
        current_user = get_jwt_identity()
        columns = ['waiter_id', 'restaurant_id', 'status', 'reservation_date', 'reservation_hour', 'persons',
                   'reservation_status']
        reservation_hour = request.form['reservation_hour']
        reservation_date = request.form['reservation_date']
        restaurant_id = request.form['restaurant_id']
        if if_reservation_available(self, reservation_date, reservation_hour, restaurant_id, reservation_id):
            col_strings, values = columns_values_creator(columns, extra_values=[current_user],
                                                         extra_columns=['user_id'])
            query = query_creator('update', 'reservations', col_strings, values, id=reservation_id)
            cur = get_db_connection()
            cur.execute(query)
            return {'Status': 201}
        else:
            return {'Status': 400, 'message': 'Reservation is not available'}

    @user_required()
    def delete(self, reservation_id):
        query = query_creator('delete', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class UserReservations(Resource):
    @admin_required()
    def get(self, user_id):
        query = query_creator('select_where', 'reservations', id=user_id, where='user_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        return jsonify(rows)

    @admin_required()
    def post(self, user_id):
        columns = ['waiter_id', 'restaurant_id', 'status', 'reservation_date', 'reservation_hour', 'persons',
                   'reservation_status']
        reservation_hour = request.form['reservation_hour']
        reservation_date = request.form['reservation_date']
        restaurant_id = request.form['restaurant_id']
        if if_reservation_available(self, reservation_date, reservation_hour, restaurant_id):
            col_strings, values = columns_values_creator(columns, extra_values=[user_id],
                                                         extra_columns=['user_id'])
            query = query_creator('insert', 'reservations', col_strings, values)
            cur = get_db_connection()
            cur.execute(query)
            return {'Status': 201}
        else:
            return {'Status': 400, 'message': 'Reservation is not available'}


class UserReservation(Resource):
    @admin_required()
    def get(self, user_id, reservation_id):
        query = query_creator('select_where', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @admin_required()
    def delete(self, user_id, reservation_id):
        query = query_creator('delete', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class Restaurants(Resource):
    # public
    def get(self):
        query = query_creator('select', 'restaurants')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)

    @admin_required()
    def post(self):
        columns = ['name', 'legal_name', 'photo', 'description', 'address', 'menu_description']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'restaurants', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 201}


class Restaurant(Resource):
    def get(self, restaurant_id):
        query = query_creator('select_where', 'restaurants', id=restaurant_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        avg_rating_query = "SELECT avg(reviews.rating) from reviews LEFT JOIN reservations as r ON r.id = reviews.reservation_id WHERE r.restaurant_id = %s " % restaurant_id
        cur.execute(avg_rating_query)
        avg = cur.fetchone()['avg']
        if avg is None:
            avg = 0
        avg_rating = "{:.2f}".format(avg)
        return jsonify({'AverageRating': avg_rating, 'Rows': rows})

    @admin_required()
    def put(self, restaurant_id):
        columns = ['name', 'legal_name', 'photo', 'description', 'address', 'menu_description']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('update', 'restaurants', col_strings, values, id=restaurant_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}

    @admin_required()
    def delete(self, restaurant_id):
        query = query_creator('delete', 'restaurants', id=restaurant_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class RestaurantsMenu(Resource):
    @restaurant_required()
    def get(self):
        id = get_jwt_identity()
        query = query_creator('select_where', 'menu_elements', id=id, where='restaurant_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)

    @restaurant_required()
    def post(self):  # add menu element
        id = get_jwt_identity()
        columns = ['name', 'description', 'price', 'photo', 'category']
        col_strings, values = columns_values_creator(columns, extra_values=[id],
                                                     extra_columns=['restaurant_id'])
        query = query_creator('insert', 'menu_elements', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 201}


class RestaurantMenuElement(Resource):
    @restaurant_required()
    def get(self, menu_element_id):
        query = query_creator('select_where', 'menu_elements', id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @restaurant_required()
    def put(self, menu_element_id):
        columns = ['name', 'description', 'price', 'photo']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('update', 'menu_elements', col_strings, values, id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}

    @restaurant_required()
    def delete(self, menu_element_id):
        query = query_creator('delete', 'menu_elements', id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class RestaurantsReviews(Resource):
    @restaurant_required()
    def get(self):
        id = get_jwt_identity()
        query = "SELECT * FROM reservations RIGHT JOIN reviews ON reviews.reservation_id = reservations.id WHERE reservations.restaurant_id = %s" % id
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        avg_rating_query = "SELECT avg(reviews.rating) from reviews LEFT JOIN reservations as r ON r.id = reviews.reservation_id WHERE r.restaurant_id = %s " % id
        cur.execute(avg_rating_query)
        avg = cur.fetchone()['avg']
        if avg is None:
            avg = 0
        avg_rating = "{:.2f}".format(avg)
        return jsonify({'AverageRating': avg_rating, 'Rows': rows})

class RestaurantReviews(Resource):
    def get(self, restaurant_id):
        # fetch restaurant and its reviews by join method
        query = "SELECT * FROM reservations RIGHT JOIN reviews ON reviews.reservation_id = reservations.id WHERE reservations.restaurant_id = %s" % restaurant_id
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        avg_rating_query = "SELECT avg(reviews.rating) from reviews LEFT JOIN reservations as r ON r.id = reviews.reservation_id WHERE r.restaurant_id = %s " % restaurant_id
        cur.execute(avg_rating_query)
        avg = cur.fetchone()['avg']
        if avg is None:
            avg = 0
        avg_rating = "{:.2f}".format(avg)
        return jsonify({'AverageRating': avg_rating, 'Rows': rows})

class RestaurantsReservations(Resource):
    @restaurant_required()
    def get(self):
        id = get_jwt_identity()
        query = query_creator('select_where', 'reservations', id=id, where='restaurant_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)


class RestaurantReservations(Resource):
    @admin_required()
    def get(self, restaurant_id):
        query = query_creator('select_where', 'reservations', id=restaurant_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)


class Waiters(Resource):
    @admin_required()
    def get(self):
        query = query_creator('select', 'waiters')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)

    @admin_required()
    def post(self):
        columns = ['name', 'surname', 'restaurant_id']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'waiters', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        return {'status': 201}


class Waiter(Resource):
    @admin_required()
    def get(self, waiter_id):
        query = query_creator('select_where', 'waiters', id=waiter_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @admin_required()
    def put(self, waiter_id):
        columns = ['name', 'surname', 'restaurant_id']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('update', 'waiters', col_strings, values, id=waiter_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'status': 200}

    @admin_required()
    def delete(self, waiter_id):
        query = query_creator('delete', 'waiters', id=waiter_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'status': 200}


class WaiterReviews(Resource):
    def get(self, waiter_id):
        query = "SELECT * FROM reservations RIGHT JOIN reviews ON reviews.reservation_id = reservations.id WHERE reservations.waiter_id = %s" % waiter_id
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        avg_rating_query = "SELECT avg(reviews.rating) from reviews LEFT JOIN reservations as r ON r.id = reviews.reservation_id WHERE r.waiter_id = %s " % waiter_id
        cur.execute(avg_rating_query)
        avg = cur.fetchone()['avg']
        if avg is None:
            avg = 0
        avg_rating = "{:.2f}".format(avg)
        return jsonify({'AverageRating': avg_rating, 'Rows': rows})


class WaiterReservations(Resource):
    @admin_required()
    def get(self, waiter_id):
        query = query_creator('select_where', 'reservations', id=waiter_id, where='waiter_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)


class Menu(Resource):
    def get(self, restaurant_id):
        query = query_creator('select_where', 'menu_elements', id=restaurant_id, where='restaurant_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)


class MenuElements(Resource):
    def get(self, restaurant_id):
        query = query_creator('select_where', 'menu_elements', id=restaurant_id, where='restaurant_id')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @admin_required()
    def post(self, restaurant_id):
        columns = ['name', 'description', 'price', 'photo']
        col_strings, values = columns_values_creator(columns, extra_values=[restaurant_id],
                                                     extra_columns=['restaurant_id'])
        query = query_creator('insert', 'menu_elements', col_strings, values)
        print(query)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 201}


class MenuElement(Resource):
    def get(self, restaurant_id, menu_element_id):
        query = query_creator('select_where', 'menu_elements', id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    def put(self, restaurant_id, menu_element_id):
        columns = ['name', 'description', 'price', 'photo']
        col_strings, values = columns_values_creator(columns, extra_values=[restaurant_id],
                                                     extra_columns=['restaurant_id'])
        query = query_creator('update', 'menu_elements', col_strings, values, id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}

    def delete(self, restaurant_id, menu_element_id):
        query = query_creator('delete', 'menu_elements', id=menu_element_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class Reviews(Resource):
    def get(self):
        query = query_creator('select', 'reviews')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        return jsonify(rows)

    @admin_required()
    def post(self):
        columns = ['reservation_id', 'comment', 'rating']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('insert', 'reviews', col_strings, values)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 201}


class Review(Resource):
    def get(self, review_id):
        query = query_creator('select_where', 'reviews', id=review_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        return jsonify(rows)

    @admin_required()
    def put(self, review_id):
        columns = ['comment', 'rating']
        col_strings, values = columns_values_creator(columns)
        query = query_creator('update', 'reviews', col_strings, values, id=review_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}

    @admin_required()
    def delete(self, review_id):
        query = query_creator('delete', 'reviews', id=review_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class Reservations(Resource):
    @admin_required()
    def get(self):
        query = query_creator('select', 'reservations')
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            row['reservation_date'] = row['reservation_date'].strftime("%Y-%m-%d")
            row['reservation_hour'] = row['reservation_hour'].strftime("%H:%M")
        return jsonify(rows)

    @admin_required()
    def post(self):
        columns = ['waiter_id', 'user_id', 'restaurant_id', 'status', 'reservation_date', 'reservation_hour', 'persons',
                   'reservation_status']
        reservation_hour = request.form['reservation_hour']
        reservation_date = request.form['reservation_date']
        restaurant_id = request.form['restaurant_id']
        if if_reservation_available(self, reservation_date, reservation_hour, restaurant_id):
            col_strings, values = columns_values_creator(columns)
            query = query_creator('insert', 'reservations', col_strings, values)
            print(query)
            cur = get_db_connection()
            cur.execute(query)
            return {'Status': 201}
        else:
            return {'Status': 400, 'message': 'Reservation is not available'}


class Reservation(Resource):
    @admin_required()
    def get(self, reservation_id):
        query = query_creator('select_where', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        rows = cur.fetchone()
        rows['reservation_date'] = rows['reservation_date'].strftime("%Y-%m-%d")
        rows['reservation_hour'] = rows['reservation_hour'].strftime("%H:%M")
        return jsonify(rows)

    @admin_required()
    def put(self, reservation_id):
        columns = ['waiter_id', 'user_id', 'restaurant_id', 'status', 'reservation_date', 'reservation_hour', 'persons',
                   'reservation_status']
        reservation_hour = request.form['reservation_hour']
        reservation_date = request.form['reservation_date']
        restaurant_id = request.form['restaurant_id']
        if if_reservation_available(self, reservation_date, reservation_hour, restaurant_id, reservation_id):
            col_strings, values = columns_values_creator(columns)
            query = query_creator('update', 'reservations', col_strings, values, id=reservation_id)
            cur = get_db_connection()
            cur.execute(query)
            return {'Status': 201}
        else:
            return {'Status': 400, 'message': 'Reservation is not available'}

    @admin_required()
    def delete(self, reservation_id):
        query = query_creator('delete', 'reservations', id=reservation_id)
        cur = get_db_connection()
        cur.execute(query)
        return {'Status': 200}


class Test(Resource):
    def get(self):
        print(timeDiffInMinutes('12:00', '13:00'))
        reservation_date = '2022-01-01'
        reservation_hour = '12:00'
        print(if_reservation_available(self, reservation_date, reservation_hour, 1))
        return 1


def timeDiffInMinutes(time1, time2):
    FMT = '%H:%M'
    tdelta = datetime.strptime(time2, FMT) - datetime.strptime(time1, FMT)
    tdelta = tdelta.seconds / 60
    return tdelta


def if_reservation_available(self, reservation_date, reservation_hour, restaurant_id, reservation_id=None):
    query = query_creator('select_where', 'reservations', id=restaurant_id, where='restaurant_id')
    query = query + " AND reservation_date = '%s'" % reservation_date
    if reservation_id is not None:
        query = query + " AND id != %s" % reservation_id
    cur = get_db_connection()
    print(query)
    cur.execute(query)
    rows = cur.fetchall()
    for row in rows:
        print('tdelta', timeDiffInMinutes(row['reservation_hour'].strftime("%H:%M"), reservation_hour))
        if timeDiffInMinutes(row['reservation_hour'].strftime("%H:%M"), reservation_hour) < 60:
            return False
    return True


# Test
# Admin-register-user login

api.add_resource(Test, '/test')

api.add_resource(AdminLogin, '/admins/login')
api.add_resource(AdminRegister, '/admins/register')

api.add_resource(RestaurantLogin, '/restaurants/login')
api.add_resource(RestaurantRegister, '/restaurants/register')

api.add_resource(Users, '/users')
api.add_resource(UserLogin, '/users/login')
api.add_resource(UserRegister, '/users/register')
api.add_resource(User, '/users/<user_id>')
api.add_resource(UserReviews, '/users/<user_id>/reviews')
api.add_resource(UserReservations, '/users/<user_id>/reservations')  # user reservations
api.add_resource(UserReservation, '/users/<user_id>/reservations/<reservation_id>')

api.add_resource(MyReviews, '/my-reviews')
api.add_resource(MyReservations, '/my-reservations')  # user reservations get-post
api.add_resource(MyReservation, '/my-reservations/<reservation_id>')  # user reservations

api.add_resource(Restaurants, '/restaurants')
api.add_resource(Restaurant, '/restaurants/<restaurant_id>')
api.add_resource(RestaurantsMenu, '/restaurants/menu')
api.add_resource(RestaurantMenuElement, '/restaurants/menu/<menu_element_id>')
api.add_resource(Menu,
                 '/restaurants/<restaurant_id>/menu')  # See the restaurant menu or Create menu if there is no menu
api.add_resource(MenuElements, '/restaurants/<restaurant_id>/menu/menu-element')  # Update or Delete or Add menu element
api.add_resource(MenuElement,
                 '/restaurants/<restaurant_id>/menu/menu-element/<menu_element_id>')  # Update or Delete or Add menu element

api.add_resource(RestaurantReviews, '/restaurants/<restaurant_id>/reviews')  # See the restaurant reviews
api.add_resource(RestaurantReservations, '/restaurants/<restaurant_id>/reservations')  # See the restaurant reservations

api.add_resource(RestaurantsReviews, '/restaurants/reviews')  # See the restaurant's reviews
api.add_resource(RestaurantsReservations, '/restaurants/reservations')  # See the restaurant's reservations

api.add_resource(Reviews, '/reviews')
api.add_resource(Review, '/reviews/<review_id>')

api.add_resource(Reservations, '/reservations')
api.add_resource(Reservation, '/reservations/<reservation_id>')

api.add_resource(Waiters, '/waiters')
api.add_resource(Waiter, '/waiters/<waiter_id>')
api.add_resource(WaiterReviews, '/waiters/<waiter_id>/reviews')

if __name__ == '__main__':
    app.run(debug=True)
